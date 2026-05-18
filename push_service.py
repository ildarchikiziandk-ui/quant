from pywebpush import webpush, WebPushException
import json

VAPID_PUBLIC_KEY = "BBP9BjUpRFFbpGIG6-QMCEqJqJMuF7B9ki0ymUFtWYRU3O7fv7Sds2jLPhHAd1mFWkiWCG0V58m3Spgy9bQWVqQ="
VAPID_PRIVATE_KEY = "LS0tLS1CRUdJTiBFQyBQUklWQVRFIEtFWS0tLS0tCk1IY0NBUUVFSUNKL2tKWmYxM2h5V09GekZ5Vzh4S2EzUEZhd3RYQjJCYUZTUjdLZ0ZqR2JvQW9HQ0NxR1NNNDkKQXdFSG9VUURRZ0FFRS8wR05TbEVVVnVrWWdicjVBd0lTb21va3k0WHNIMlNMVEtaUVcxWmhGVGM3dCsvdEoyegphTXMrRWNCM1dZVmFTSllJYlJYbnliZEttREwxdEJaV3BBPT0KLS0tLS1FTkQgRUMgUFJJVkFURSBLRVktLS0tLQo="
VAPID_EMAIL = "mailto:quantru@internet.ru"

def send_push(subscription_info: dict, title: str, body: str, url: str = "/"):
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_EMAIL}
        )
        return True
    except WebPushException as e:
        print(f"Push error: {e}")
        return False

def send_push_to_user(user, db, title: str, body: str, url: str = "/"):
    from models import PushSubscription
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user.id).all()
    for sub in subs:
        try:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {
                    "p256dh": sub.p256dh,
                    "auth": sub.auth
                }
            }
            send_push(subscription_info, title, body, url)
        except:
            pass