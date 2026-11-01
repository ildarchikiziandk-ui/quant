package ru.nvra.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.webkit.CookieManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import java.net.HttpURLConnection
import java.net.URL

/**
 * Входящий звонок как настоящий звонок: отдельный канал с мелодией звонка и вибрацией, экран поверх блокировки
 * и кнопки «Ответить» / «Отклонить». Звенит, пока не ответили, не отклонили или не прошло 45 секунд.
 */
object CallNotify {
    const val CHANNEL = "nuvora_calls_v1"  // настройки канала после создания не меняются — при правке звука нужен новый id
    const val EXTRA_CALL = "call_id"
    const val EXTRA_NOTIF = "notif_id"
    private const val RING_MS = 45_000L

    fun createChannel(ctx: Context) {
        if (Build.VERSION.SDK_INT < 26) return
        val ch = NotificationChannel(CHANNEL, "Звонки", NotificationManager.IMPORTANCE_HIGH)
        ch.description = "Входящие звонки в Nuvora"
        ch.setSound(
            RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE),
            AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
        )
        ch.enableVibration(true)
        ch.vibrationPattern = longArrayOf(0, 800, 600, 800, 600, 800)
        ch.lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    fun show(ctx: Context, notifId: Int, callId: Int, who: String, path: String) {
        createChannel(ctx)
        val open = Intent(ctx, MainActivity::class.java)
            .putExtra(NotifyWorker.EXTRA_PATH, path)
            .putExtra(EXTRA_CALL, callId)
            .putExtra(EXTRA_NOTIF, notifId)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val answer = PendingIntent.getActivity(ctx, notifId, open, flags)
        val decline = PendingIntent.getBroadcast(
            ctx, notifId,
            Intent(ctx, CallActionReceiver::class.java).putExtra(EXTRA_CALL, callId).putExtra(EXTRA_NOTIF, notifId), flags
        )
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(who)
            .setContentText("Входящий звонок в Nuvora")
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setAutoCancel(true)
            .setTimeoutAfter(RING_MS)
            .setContentIntent(answer)
            .setFullScreenIntent(answer, true)  // на заблокированном экране сразу открывается экран звонка
            .addAction(0, "Отклонить", decline)
            .addAction(0, "Ответить", answer)
            .build()
        n.flags = n.flags or Notification.FLAG_INSISTENT  // мелодия повторяется, пока не ответили
        try {
            NotificationManagerCompat.from(ctx).notify(notifId, n)
        } catch (e: SecurityException) {
            // уведомления запрещены пользователем
        }
    }

    fun cancel(ctx: Context, notifId: Int) {
        if (notifId != 0) NotificationManagerCompat.from(ctx).cancel(notifId)
    }
}

/** Кнопка «Отклонить» в уведомлении: сообщаем серверу и убираем звонок, не открывая приложение. */
class CallActionReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val callId = intent.getIntExtra(CallNotify.EXTRA_CALL, 0)
        CallNotify.cancel(ctx, intent.getIntExtra(CallNotify.EXTRA_NOTIF, 0))
        if (callId == 0) return
        val done = goAsync()
        Thread {
            try {
                val conn = URL(BuildConfig.SITE_URL + "/v3/call/$callId/signal").openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.connectTimeout = 10000
                conn.readTimeout = 10000
                conn.setRequestProperty("Cookie", CookieManager.getInstance().getCookie(BuildConfig.SITE_URL) ?: "")
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("X-Requested-With", "fetch")
                conn.outputStream.use { it.write("{\"kind\":\"decline\"}".toByteArray()) }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                // нет сети — звонок сам закончится через минуту
            } finally {
                done.finish()
            }
        }.start()
    }
}
