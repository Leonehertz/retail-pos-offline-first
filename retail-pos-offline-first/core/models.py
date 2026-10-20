import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class SyncableModel(models.Model):
    """
    Clase base abstracta para modelos distribuidos Offline-First.
    Utiliza UUID4 como identificador global único para prevenir colisiones de IDs
    entre sucursales locales y el servidor central en la nube.
    """
    edited_at = models.DateTimeField(null=True, blank=True)
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.edited_at or not getattr(self, '_sync', False):
            self.edited_at = timezone.now()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Patrón Tombstone (Eliminación lógica/rastreo):
        Registra la eliminación antes de purgar el registro para propagar la baja
        hacia el servidor central durante la próxima sincronización.
        """
        external_id = self.external_id
        nombre = getattr(self, 'nombre', str(self.id))
        super().delete(*args, **kwargs)
        TombstoneDeletion.objects.create(
            modelo=self.__class__.__name__.lower(),
            target_external_id=external_id,
            nombre=nombre,
            fecha=timezone.now()
        )

class TombstoneDeletion(models.Model):
    modelo = models.CharField(max_length=60)
    target_external_id = models.UUIDField()
    nombre = models.CharField(max_length=150, null=True, blank=True)
    fecha = models.DateTimeField(default=timezone.now)

class LocalSucursal(SyncableModel):
    nombre = models.CharField(max_length=60, unique=True)
    direccion = models.CharField(max_length=120)
    telefono = models.CharField(max_length=20, default="+56 2 0000 0000")

    def __str__(self):
        return f"{self.nombre} ({self.external_id})"

class POSCaja(SyncableModel):
    identificador_caja = models.IntegerField(unique=True)
    local = models.ForeignKey(LocalSucursal, on_delete=models.CASCADE, related_name="cajas")

class TurnoCajero(models.Model):
    vendedor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos")
    pos = models.ForeignKey(POSCaja, on_delete=models.CASCADE)
    hora_inicio = models.DateTimeField(default=timezone.now)
    hora_fin = models.DateTimeField(null=True, blank=True)
    fondo_de_caja = models.IntegerField(default=0)
    efectivo_final = models.IntegerField(default=0)
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

class Producto(SyncableModel):
    nombre = models.CharField(max_length=150)
    codigo = models.CharField(max_length=100, unique=True)
    usa_stock = models.BooleanField(default=True)
    habilitado = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"

class StockPorLocal(SyncableModel):
    """
    Mapeo de inventario dinámico por sucursal física.
    Asegura unicidad estricta y control de consistencia transaccional.
    """
    local = models.ForeignKey(LocalSucursal, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="stocks_por_local")
    stock_disponible = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = ['local', 'producto']

class Venta(models.Model):
    id = models.BigIntegerField(primary_key=True, unique=True, editable=False)
    turno = models.ForeignKey(TurnoCajero, on_delete=models.CASCADE, related_name="ventas")
    pos = models.ForeignKey(POSCaja, on_delete=models.CASCADE)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_unidades = models.IntegerField(default=1)
    fecha = models.DateTimeField(default=timezone.now)
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

class LineaVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField(default=1)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
