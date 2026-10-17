package ru.nvra.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.webkit.CookieManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/** Раз в ~15 минут проверяет новые сообщения и уведомления и показывает системное уведомление. */
class NotifyWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        try {
            val cookie = CookieManager.getInstance().getCookie(BuildConfig.SITE_URL) ?: return Result.success()
            if (!cookie.contains("token=")) return Result.success()
            val conn = URL(BuildConfig.SITE_URL + "/api/counters?bg=1").openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            conn.setRequestProperty("Cookie", cookie)
            conn.setRequestProperty("X-Requested-With", "fetch")
            if (conn.responseCode != 200) return Result.success()
            val json = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
            conn.disconnect()
            val messages = json.optInt("messages")
            val notifications = json.optInt("notifications")
            val prefs = applicationContext.getSharedPreferences("notify", Context.MODE_PRIVATE)
            // служба мгновенных уведомлений работает — она уже всё показала, только перезапускаем её на всякий случай
            if (System.currentTimeMillis() - prefs.getLong("stream_ok", 0L) < 5 * 60 * 1000L) {
                prefs.edit().putInt("messages", messages).putInt("notifications", notifications).apply()
                return Result.success()
            }
            NotifyService.start(applicationContext)
            if (messages > prefs.getInt("messages", 0)) {
                show(1, "Новые сообщения", "Непрочитанных сообщений: $messages", "/messages")
            }
            if (notifications > prefs.getInt("notifications", 0)) {
                show(2, "Новые уведомления", "Непрочитанных уведомлений: $notifications", "/notifications")
            }
            prefs.edit().putInt("messages", messages).putInt("notifications", notifications).apply()
        } catch (e: Exception) {
            // нет сети или сервер недоступен — попробуем в следующий раз
        }
        return Result.success()
    }

    private fun show(id: Int, title: String, text: String, path: String) {
        val ctx = applicationContext
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        if (Build.VERSION.SDK_INT >= 26) {
            val channel = NotificationChannel(CHANNEL, ctx.getString(R.string.channel_name), NotificationManager.IMPORTANCE_DEFAULT)
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val intent = Intent(ctx, MainActivity::class.java)
            .putExtra(EXTRA_PATH, path)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pending = PendingIntent.getActivity(ctx, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        try {
            NotificationManagerCompat.from(ctx).notify(id, notification)
        } catch (e: SecurityException) {
            // уведомления запрещены пользователем
        }
    }

    companion object {
        const val CHANNEL = "nuvora_updates"
        const val EXTRA_PATH = "path"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<NotifyWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("nuvora-notify", ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
