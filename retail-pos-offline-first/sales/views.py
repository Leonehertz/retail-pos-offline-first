from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from core.models import POSCaja, TurnoCajero, Producto, StockPorLocal, Venta, LineaVenta

class RegistrarVentaAPIView(APIView):
    """
    Endpoint de alta concurrencia para registro de transacciones en caja.
    Aplica bloqueo pesimista y transacciones atómicas para prevenir condiciones de carrera (Race Conditions)
    y evitar quiebres de stock o sobreventas en cajas simultáneas de la misma sucursal.
    """

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        pos_id = request.data.get("pos_id")
        lineas_data = request.data.get("lineas", [])
        
        pos = POSCaja.objects.filter(identificador_caja=pos_id).select_related('local').first()
        if not pos:
            return Response({"error": "POS no registrado en esta sucursal"}, status=status.HTTP_404_NOT_FOUND)

        turno_activo = TurnoCajero.objects.filter(pos=pos, hora_fin__isnull=True).last()
        if not turno_activo:
            raise ValidationError({"detail": "No existe un turno de cajero activo para esta caja."})

        # 1. Validación estricta y bloqueo de stock disponible
        total_acumulado = Decimal('0.00')
        total_unidades = 0
        lineas_validadas = []

        for item in lineas_data:
            producto_codigo = item.get("producto_codigo")
            cantidad_solicitada = int(item.get("cantidad", 1))

            # Bloqueo select_for_update() a nivel de fila para garantizar integridad en bases de datos concurrentes
            stock_record = StockPorLocal.objects.select_for_update().filter(
                local=pos.local,
                producto__codigo=producto_codigo
            ).select_related('producto').first()

            if not stock_record:
                raise ValidationError({"detail": f"Producto {producto_codigo} no tiene registro de stock en este local."})

            producto = stock_record.producto

            if producto.usa_stock and stock_record.stock_disponible < cantidad_solicitada:
                raise ValidationError({
                    "detail": f"Stock insuficiente para '{producto.nombre}'. "
                              f"Disponible: {stock_record.stock_disponible}, Solicitado: {cantidad_solicitada}"
                })

            # Descontar stock atómicamente
            if producto.usa_stock:
                stock_record.stock_disponible -= Decimal(cantidad_solicitada)
                stock_record.save()

            subtotal = Decimal(str(item.get("precio_unitario", "0"))) * Decimal(cantidad_solicitada)
            total_acumulado += subtotal
            total_unidades += cantidad_solicitada

            lineas_validadas.append({
                "producto": producto,
                "cantidad": cantidad_solicitada,
                "subtotal": subtotal
            })

        # 2. Persistir Cabecera de Venta
        venta = Venta.objects.create(
            id=int(timezone.now().timestamp() * 1000), # Generación de ID transaccional único
            turno=turno_activo,
            pos=pos,
            total=total_acumulado,
            cantidad_unidades=total_unidades,
            fecha=timezone.now()
        )

        # 3. Persistir Detalle de Líneas
        for linea in lineas_validadas:
            LineaVenta.objects.create(
                venta=venta,
                producto=linea["producto"],
                cantidad=linea["cantidad"],
                subtotal=linea["subtotal"]
            )

        return Response({
            "status": "success",
            "venta_id": venta.id,
            "total": float(venta.total),
            "unidades": venta.cantidad_unidades,
            "mensaje": "Venta procesada y stock actualizado atómicamente."
        }, status=status.HTTP_201_CREATED)
