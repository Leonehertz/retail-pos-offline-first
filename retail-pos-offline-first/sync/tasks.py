import os
import requests
from django.conf import settings
from django.db import transaction
from celery import shared_task
from rest_framework.exceptions import APIException
from core.models import LocalSucursal, Producto, StockPorLocal, Venta, LineaVenta

# Configuración de URLs y Tokens desde variables de entorno seguras
CLOUD_SERVER_URL = os.getenv("MAIN_SERVER_URL", "https://api.cloud-server.com")
SYNC_TOKEN = os.getenv("POS_SYNC_TOKEN", "mock-token-for-dev")

SYNC_HEADERS = {
    "Authorization": f"Bearer {SYNC_TOKEN}",
    "Content-Type": "application/json"
}

@shared_task
def sync_catalogs_from_cloud():
    """
    Tarea periódica de sincronización Offline-First (Local Node <--- Cloud Server).
    Descarga catálogos de productos, precios y stocks asignados a esta sucursal.
    Utiliza transacciones atómicas (ACID) para evitar estados inconsistentes en caso
    de interrupciones de red durante la sincronización.
    """
    entities = ['sucursal', 'producto', 'stock_local']
    
    with transaction.atomic():
        for entity in entities:
            try:
                response = requests.get(
                    f"{CLOUD_SERVER_URL}/api/sync/delta/{entity}/",
                    headers=SYNC_HEADERS,
                    timeout=15
                )
                if response.status_code != 200:
                    continue

                items = response.json().get("data", [])
                for item in items:
                    if entity == 'producto':
                        Producto.objects.update_or_create(
                            codigo=item.get("codigo"),
                            defaults={
                                "nombre": item.get("nombre"),
                                "usa_stock": item.get("usa_stock", True),
                                "habilitado": item.get("habilitado", True)
                            }
                        )
                    elif entity == 'stock_local':
                        local_inst = LocalSucursal.objects.filter(external_id=item.get("local_external_id")).first()
                        prod_inst = Producto.objects.filter(codigo=item.get("producto_codigo")).first()
                        if local_inst and prod_inst:
                            StockPorLocal.objects.update_or_create(
                                local=local_inst,
                                producto=prod_inst,
                                defaults={"stock_disponible": item.get("stock_disponible", 0)}
                            )
            except requests.RequestException as e:
                # Si se cae la conexión, el nodo local continúa operando normalmente
                # y reintentará en el próximo ciclo programado.
                print(f"[Offline Mode] Sync temporalmente postergada para {entity}: {e}")

@shared_task
def push_pending_sales_to_cloud():
    """
    Sincronización saliente (Local Node ---> Cloud Server).
    Empuja las transacciones generadas offline hacia el servidor central
    para conciliación financiera y deducción global de inventarios.
    """
    pending_sales = Venta.objects.filter(sincronizada_con_nube=False)[:50]
    if not pending_sales.exists():
        return "No pending transactions"

    payload = []
    for venta in pending_sales:
        payload.append({
            "external_id": str(venta.external_id),
            "pos_caja": venta.pos.identificador_caja,
            "total": float(venta.total),
            "fecha": venta.fecha.isoformat(),
            "lineas": [
                {
                    "producto_codigo": linea.producto.codigo,
                    "cantidad": linea.cantidad,
                    "subtotal": float(linea.subtotal)
                } for linea in venta.lineas.all()
            ]
        })

    try:
        res = requests.post(
            f"{CLOUD_SERVER_URL}/api/sync/ingest-sales/",
            json={"ventas": payload},
            headers=SYNC_HEADERS,
            timeout=20
        )
        if res.status_code == 200:
            with transaction.atomic():
                confirmed_ids = res.json().get("confirmed_external_ids", [])
                Venta.objects.filter(external_id__in=confirmed_ids).update(sincronizada_con_nube=True)
            return f"Synchronized {len(confirmed_ids)} sales successfully"
    except requests.RequestException as err:
        print(f"[Network Latency] Fallo al subir ventas a la nube: {err}")
        return "Sync retry scheduled"
