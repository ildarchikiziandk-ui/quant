package ru.nvra.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Обновление изнутри приложения: спрашивает у сайта номер последней сборки (/api/app/latest),
 * скачивает APK с сайта и открывает системный установщик. На GitHub пользователь не попадает.
 */
class Updater(private val act: AppCompatActivity) {
    private val prefs = act.getSharedPreferences("nuvora_update", Context.MODE_PRIVATE)
    private var pending: File? = null  // скачано, ждём разрешения «устанавливать из этого источника»
    @Volatile private var busy = false

    /** Тихая проверка не чаще раза в 6 часов; [manual] — по кнопке «Проверить обновления». */
    fun check(manual: Boolean = false) {
        if (busy) return
        val now = System.currentTimeMillis()
        if (!manual && now - prefs.getLong("checked", 0) < 6 * 3600_000L) return
        busy = true
        Thread {
            try {
                val c = URL(BuildConfig.SITE_URL + "/api/app/latest").openConnection() as HttpURLConnection
                c.connectTimeout = 8000
                c.readTimeout = 8000
                val j = if (c.responseCode == 200) JSONObject(c.inputStream.bufferedReader().use { it.readText() }) else null
                c.disconnect()
                prefs.edit().putLong("checked", now).apply()
                val code = j?.optInt("version_code") ?: 0
                act.runOnUiThread {
                    when {
                        j == null || code <= 0 -> if (manual) toast("Не удалось проверить обновления")
                        code <= BuildConfig.VERSION_CODE -> if (manual) toast("У вас последняя версия")
                        !manual && prefs.getInt("later", 0) == code && now - prefs.getLong("later_at", 0) < 24 * 3600_000L -> Unit
                        else -> ask(code, j!!.optString("version"), j.optString("url"))
                    }
                }
            } catch (e: Exception) {
                if (manual) act.runOnUiThread { toast("Нет связи с сервером") }
            } finally {
                busy = false
            }
        }.start()
    }

    private fun ask(code: Int, version: String, url: String) {
        if (act.isFinishing) return
        AlertDialog.Builder(act)
            .setTitle("Доступно обновление")
            .setMessage("Вышла Nuvora $version с новыми функциями и исправлениями. Обновление займёт минуту — переписка и вход сохранятся.")
            .setPositiveButton("Обновить") { _, _ -> download(code, url) }
            .setNegativeButton("Позже") { _, _ -> prefs.edit().putInt("later", code).putLong("later_at", System.currentTimeMillis()).apply() }
            .show()
    }

    private fun download(code: Int, url: String) {
        val bar = ProgressBar(act, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100; isIndeterminate = true }
        val label = TextView(act).apply { text = "Скачиваем…"; setPadding(0, 0, 0, 16) }
        val box = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(64, 32, 64, 8); addView(label); addView(bar) }
        val dlg = AlertDialog.Builder(act).setTitle("Обновление Nuvora").setView(box).setCancelable(false).show()
        Thread {
            val dir = File(act.cacheDir, "updates").apply { mkdirs() }
            dir.listFiles()?.forEach { it.delete() }
            val file = File(dir, "Nuvora-$code.apk")
            try {
                var link = url
                var conn: HttpURLConnection
                var hops = 0
                while (true) {  // сайт может перенаправить на зеркало; следуем вручную (https → https)
                    conn = URL(link).openConnection() as HttpURLConnection
                    conn.instanceFollowRedirects = false
                    conn.connectTimeout = 15000
                    conn.readTimeout = 30000
                    val rc = conn.responseCode
                    if (rc in 300..399 && hops++ < 5) {
                        link = URL(URL(link), conn.getHeaderField("Location")).toString()
                        conn.disconnect()
                        if (!link.startsWith("https://")) throw IllegalStateException("insecure redirect")
                        continue
                    }
                    if (rc != 200) throw IllegalStateException("HTTP $rc")
                    break
                }
                val total = conn.contentLengthLong
                var done = 0L
                conn.inputStream.use { input ->
                    file.outputStream().use { out ->
                        val buf = ByteArray(64 * 1024)
                        var last = -1
                        while (true) {
                            val n = input.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            done += n
                            if (total > 0) {
                                val p = (done * 100 / total).toInt()
                                if (p != last) {
                                    last = p
                                    act.runOnUiThread { bar.isIndeterminate = false; bar.progress = p; label.text = "Скачиваем… $p%" }
                                }
                            }
                        }
                    }
                }
                conn.disconnect()
                if (total > 0 && done != total) throw IllegalStateException("incomplete")
                act.runOnUiThread { dlg.dismiss(); install(file) }
            } catch (e: Exception) {
                file.delete()
                act.runOnUiThread { dlg.dismiss(); toast("Не удалось скачать обновление. Попробуйте позже") }
            }
        }.start()
    }

    private fun install(file: File) {
        if (Build.VERSION.SDK_INT >= 26 && !act.packageManager.canRequestPackageInstalls()) {
            pending = file
            AlertDialog.Builder(act)
                .setTitle("Разрешите установку")
                .setMessage("Чтобы обновиться, разрешите Nuvora устанавливать приложения: включите переключатель и вернитесь назад.")
                .setPositiveButton("Открыть настройки") { _, _ ->
                    try {
                        act.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + act.packageName)))
                    } catch (e: Exception) {
                        toast("Откройте настройки телефона → Приложения → Nuvora → «Установка неизвестных приложений»")
                    }
                }
                .setNegativeButton("Отмена", null)
                .show()
            return
        }
        pending = null
        val uri = FileProvider.getUriForFile(act, act.packageName + ".updates", file)
        val intent = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            act.startActivity(intent)
        } catch (e: Exception) {
            toast("Не удалось открыть установщик")
        }
    }

    /** Вызывать из onResume: пользователь вернулся из настроек с разрешением — продолжаем установку. */
    fun resume() {
        val f = pending ?: return
        if (Build.VERSION.SDK_INT < 26 || act.packageManager.canRequestPackageInstalls()) {
            if (f.exists()) install(f) else pending = null
        }
    }

    private fun toast(t: String) = Toast.makeText(act, t, Toast.LENGTH_LONG).show()
}
