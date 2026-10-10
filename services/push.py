"""Web Push уведомления. Работает только если заданы VAPID-ключи и установлен pywebpush."""
import json
import threading

import config

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = Exception

ENABLED = bool(webpush and config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY)


def _send(subs, payload):
    from database import SessionLocal
    import models
    dead = []
    for sub_id, info in subs:
        try:
            webpush(subscription_info=info, data=payload, vapid_private_key=config.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": config.VAPID_EMAIL}, timeout=10)
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                dead.append(sub_id)
        except Exception as e:
            print(f"Push error: {e}")
    if dead:
        db = SessionLocal()
        try:
            db.query(models.PushSubscription).filter(models.PushSubscription.id.in_(dead)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def send_push_to_user(user_id, db, title, body, url="/"):
    if not ENABLED:
        return
    import models
    subs = [(s.id, {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}})
            for s in db.query(models.PushSubscription).filter(models.PushSubscription.user_id == user_id).all()]
    if not subs:
        return
    payload = json.dumps({"title": title, "body": body, "url": url})
    threading.Thread(target=_send, args=(subs, payload), daemon=True).start()
