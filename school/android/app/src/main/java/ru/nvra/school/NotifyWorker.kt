package ru.nvra.school

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

/** Раз в ~15 минут спрашивает у сайта, что нового (оценки, поведение, задания, сообщения), и показывает уведомление. */
class NotifyWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        try {
            val cookie = CookieManager.getInstance().getCookie(BuildConfig.SITE_URL) ?: return Result.success()
            if (!cookie.contains("school_sid=")) return Result.success()
            val conn = URL(BuildConfig.SITE_URL + "/api/updates").openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            conn.setRequestProperty("Cookie", cookie)
            conn.setRequestProperty("X-Requested-With", "fetch")
            if (conn.responseCode != 200) return Result.success()
            val j = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
            conn.disconnect()
            val prefs = applicationContext.getSharedPreferences("notify", Context.MODE_PRIVATE)
            val first = !prefs.getBoolean("init", false)  // первый запуск: запоминаем, что уже есть, и не шумим
            val ed = prefs.edit().putBoolean("init", true)
            fun fresh(key: String): JSONObject? {
                val o = j.optJSONObject(key) ?: return null
                val id = o.optInt("id")
                if (id <= prefs.getInt(key, 0)) return null
                ed.putInt(key, id)
                return if (first) null else o
            }
            fresh("last_message")?.let { o ->
                val who = o.optString("from").ifBlank { "Учитель" }
                show(1, "Сообщение: $who", o.optString("text"), o.optString("url", "/"))
            }
            fresh("last_grade")?.let { o ->
                show(2, "Новая оценка: ${o.optInt("value")}", o.optString("subject"), o.optString("url", "/s/grades"))
            }
            fresh("last_behavior")?.let { o ->
                show(3, "Поведение: ${o.optInt("value")} — ${o.optString("label")}", "Учитель поставил оценку за поведение", o.optString("url", "/s/behavior"))
            }
            fresh("last_homework")?.let { o ->
                show(4, "Новое задание", o.optString("subject"), o.optString("url", "/s/homework"))
            }
            ed.apply()
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
            val ch = NotificationChannel(CHANNEL, ctx.getString(R.string.channel_name), NotificationManager.IMPORTANCE_HIGH)
            ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
        }
        val intent = Intent(ctx, MainActivity::class.java)
            .putExtra(EXTRA_PATH, path)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pending = PendingIntent.getActivity(ctx, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat)
            .setColor(0xFF1F6FB8.toInt())
            .setContentTitle(title)
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(pending)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        try {
            NotificationManagerCompat.from(ctx).notify(id, n)
        } catch (e: SecurityException) {
            // уведомления запрещены пользователем
        }
    }

    companion object {
        const val CHANNEL = "school_updates"
        const val EXTRA_PATH = "path"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<NotifyWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork("school-notify", ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
