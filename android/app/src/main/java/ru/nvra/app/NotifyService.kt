package ru.nvra.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.webkit.CookieManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Держит связь с сервером, пока приложение свёрнуто: долгий запрос /api/stream отвечает сразу,
 * как только пришло сообщение или уведомление, и мы показываем его без задержки.
 */
class NotifyService : Service() {

    @Volatile
    private var running = false
    private var worker: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createChannels(this)
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val ongoing = NotificationCompat.Builder(this, CHANNEL_SERVICE)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("Nuvora на связи")
            .setContentText("Сообщения придут сразу")
            .setContentIntent(open)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
        try {
            val type = if (Build.VERSION.SDK_INT >= 34) ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING else 0
            ServiceCompat.startForeground(this, ONGOING_ID, ongoing, type)
        } catch (e: Exception) {
            // система не дала запустить службу (например, из фона) — останется проверка раз в 15 минут
            stopSelf()
            return START_NOT_STICKY
        }
        if (!running) {
            running = true
            worker = Thread({ loop() }, "nuvora-stream").also { it.start() }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        worker?.interrupt()
        super.onDestroy()
    }

    private fun loop() {
        val prefs = getSharedPreferences("notify", Context.MODE_PRIVATE)
        var delay = 2000L
        while (running) {
            try {
                val cookie = CookieManager.getInstance().getCookie(BuildConfig.SITE_URL)
                if (cookie == null || !cookie.contains("token=")) {
                    Thread.sleep(60000)
                    continue
                }
                val sn = prefs.getInt("stream_notif", -1)
                val sm = prefs.getInt("stream_msg", -1)
                val conn = URL(BuildConfig.SITE_URL + "/api/stream?since_notif=$sn&since_msg=$sm&wait=25").openConnection() as HttpURLConnection
                conn.connectTimeout = 15000
                conn.readTimeout = 40000
                conn.setRequestProperty("Cookie", cookie)
                conn.setRequestProperty("X-Requested-With", "fetch")
                val code = conn.responseCode
                if (code == 401) {
                    conn.disconnect()
                    Thread.sleep(60000)
                    continue
                }
                if (code != 200) {
                    conn.disconnect()
                    throw IllegalStateException("HTTP $code")
                }
                val json = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
                conn.disconnect()
                val events = json.optJSONArray("events")
                if (events != null && sn >= 0 && sm >= 0) {
                    for (i in 0 until events.length()) {
                        val e = events.getJSONObject(i)
                        val isMessage = e.optString("kind") == "message"
                        if (isMessage && appVisible) continue
                        show(
                            this,
                            if (isMessage) ("chat:" + e.optString("chat")).hashCode() else 100000 + e.optInt("id"),
                            e.optString("title"), e.optString("text"), e.optString("url", "/notifications"), isMessage
                        )
                    }
                }
                prefs.edit().putLong("stream_ok", System.currentTimeMillis()).putInt("stream_notif", json.optInt("notif", sn)).putInt("stream_msg", json.optInt("msg", sm)).apply()
                delay = 2000L
            } catch (e: InterruptedException) {
                return
            } catch (e: Exception) {
                // нет сети или сервер перезапускается — пробуем снова, всё реже
                try {
                    Thread.sleep(delay)
                } catch (ie: InterruptedException) {
                    return
                }
                delay = minOf(delay * 2, 120000L)
            }
        }
    }

    companion object {
        const val CHANNEL_SERVICE = "nuvora_service"
        const val CHANNEL_MESSAGES = "nuvora_messages"
        private const val ONGOING_ID = 7

        /** Приложение на экране — сообщения и так видны, системные уведомления о них не нужны. */
        @Volatile
        var appVisible = false

        fun start(context: Context) {
            try {
                ContextCompat.startForegroundService(context, Intent(context, NotifyService::class.java))
            } catch (e: Exception) {
                // запуск из фона запрещён системой — включится при следующем открытии приложения
            }
        }

        fun createChannels(ctx: Context) {
            if (Build.VERSION.SDK_INT < 26) return
            val nm = ctx.getSystemService(NotificationManager::class.java)
            val service = NotificationChannel(CHANNEL_SERVICE, "Связь с сервером", NotificationManager.IMPORTANCE_MIN)
            service.setShowBadge(false)
            nm.createNotificationChannel(service)
            nm.createNotificationChannel(NotificationChannel(CHANNEL_MESSAGES, "Сообщения", NotificationManager.IMPORTANCE_HIGH))
            nm.createNotificationChannel(NotificationChannel(NotifyWorker.CHANNEL, ctx.getString(R.string.channel_name), NotificationManager.IMPORTANCE_DEFAULT))
        }

        fun show(ctx: Context, id: Int, title: String, text: String, path: String, message: Boolean) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) return
            createChannels(ctx)
            val intent = Intent(ctx, MainActivity::class.java)
                .putExtra(NotifyWorker.EXTRA_PATH, path)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val pending = PendingIntent.getActivity(ctx, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val n = NotificationCompat.Builder(ctx, if (message) CHANNEL_MESSAGES else NotifyWorker.CHANNEL)
                .setSmallIcon(R.drawable.ic_stat)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText(text))
                .setContentIntent(pending)
                .setAutoCancel(true)
                .setPriority(if (message) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
                .setCategory(if (message) NotificationCompat.CATEGORY_MESSAGE else NotificationCompat.CATEGORY_SOCIAL)
                .build()
            try {
                NotificationManagerCompat.from(ctx).notify(id, n)
            } catch (e: SecurityException) {
                // уведомления запрещены пользователем
            }
        }
    }
}
