package ru.nvra.app

import android.content.Context
import android.net.Uri
import android.webkit.WebResourceResponse
import org.json.JSONObject
import java.io.IOException

/**
 * Файлы сайта внутри APK (их кладёт tools/bundle_app.py в assets/www): стили, скрипты, иконки, эмодзи, подарки.
 * Файл с версией (?v=…) отдаётся из APK, только если версия совпадает с встроенной — после обновления сайта
 * приложение само возьмёт свежий файл из сети. Файлы без версии (эмодзи, картинки) отдаются всегда.
 */
class BundledAssets(private val context: Context) {
    private val files: Map<String, String> by lazy {
        try {
            val json = context.assets.open("www/manifest.json").bufferedReader().use { it.readText() }
            val obj = JSONObject(json).getJSONObject("files")
            obj.keys().asSequence().associateWith { obj.getString(it) }
        } catch (e: Exception) {
            emptyMap()
        }
    }

    fun response(url: Uri): WebResourceResponse? {
        val path = url.path ?: return null
        if (!path.startsWith("/static/") || path.contains("..")) return null
        val want = files[path] ?: return null
        if (want != "*" && url.getQueryParameter("v") != want) return null
        return try {
            val stream = context.assets.open("www$path")
            val headers = mapOf("Cache-Control" to "public, max-age=31536000, immutable", "Access-Control-Allow-Origin" to "*")
            val mime = mimeOf(path)
            val enc = if (mime.startsWith("text/") || mime.endsWith("javascript") || mime.endsWith("svg+xml") || mime.endsWith("json")) "utf-8" else null
            WebResourceResponse(mime, enc, 200, "OK", headers, stream)
        } catch (e: IOException) {
            null
        }
    }

    /** Офлайн-экран из APK: «Нет сети», сохранённые страницы и 2048 без интернета. */
    fun offlinePage(): String? = try {
        context.assets.open("www/offline.html").bufferedReader().use { it.readText() }
    } catch (e: IOException) {
        null
    }

    private fun mimeOf(path: String): String = when (path.substringAfterLast('.', "").lowercase()) {
        "css" -> "text/css"
        "js" -> "application/javascript"
        "svg" -> "image/svg+xml"
        "png" -> "image/png"
        "jpg", "jpeg" -> "image/jpeg"
        "webp" -> "image/webp"
        "gif" -> "image/gif"
        "json" -> "application/json"
        "woff2" -> "font/woff2"
        "mp3" -> "audio/mpeg"
        else -> "application/octet-stream"
    }
}
