package ru.nvra.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.PowerManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.content.ContentValues
import android.provider.MediaStore
import android.util.Base64
import android.provider.Settings
import android.graphics.Color
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.widget.FrameLayout
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.ServiceWorkerClient
import android.webkit.ServiceWorkerController
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private lateinit var root: FrameLayout
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingPermission: PermissionRequest? = null
    private var showingOffline = false
    private val bundle by lazy { BundledAssets(this) }

    private val fileChooser = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val callback = fileCallback
        fileCallback = null
        val data = result.data
        var uris: Array<Uri>? = null
        if (result.resultCode == RESULT_OK && data != null) {
            val clip = data.clipData
            uris = if (clip != null && clip.itemCount > 0) {
                Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
            } else {
                data.data?.let { arrayOf(it) }
            }
        }
        callback?.onReceiveValue(uris)
    }

    private val mediaPermissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        val request = pendingPermission ?: return@registerForActivityResult
        pendingPermission = null
        grantAllowed(request)
    }

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            NotifyService.start(this)
            askBatteryOnce()
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        root = FrameLayout(this)
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)

        // Android 15 рисует приложение под строкой состояния и панелью навигации — отодвигаем сайт от системных панелей
        // (и от клавиатуры), а цвет полос под ними берём из темы сайта.
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            WindowInsetsCompat.CONSUMED
        }
        val nightMode = resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK
        applyTheme(nightMode == android.content.res.Configuration.UI_MODE_NIGHT_YES, null)
        web.addJavascriptInterface(ThemeBridge(), "NuvoraApp")

        val cookies = CookieManager.getInstance()
        cookies.setAcceptCookie(true)
        cookies.setAcceptThirdPartyCookies(web, true)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            offscreenPreRaster = true  // заранее рисует соседние участки страницы — прокрутка без рывков
            userAgentString = "$userAgentString NuvoraApp/${BuildConfig.VERSION_NAME}"
            cacheMode = if (isOnline()) WebSettings.LOAD_DEFAULT else WebSettings.LOAD_CACHE_ELSE_NETWORK
        }
        // стили, скрипты, иконки и эмодзи — из самого приложения: мгновенно и без сети
        ServiceWorkerController.getInstance().setServiceWorkerClient(object : ServiceWorkerClient() {
            override fun shouldInterceptRequest(request: WebResourceRequest): WebResourceResponse? = bundled(request)
        })
        watchNetwork()

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (isOwn(uri) || isAuthHost(uri)) return false  // вход через Яндекс идёт внутри приложения, чтобы cookie остались здесь
                openExternal(uri)
                return true
            }

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? = bundled(request)

            override fun onPageStarted(view: WebView, url: String, favicon: android.graphics.Bitmap?) {
                if (!url.endsWith("/offline")) showingOffline = false
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                // после входа включаем мгновенные уведомления (служба сама выключается, когда пользователь вышел)
                val c = CookieManager.getInstance().getCookie(BuildConfig.SITE_URL)
                if (c != null && c.contains("token=") && !NotifyService.running) NotifyService.start(this@MainActivity)
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) {
                    showingOffline = true
                    view.loadDataWithBaseURL(BuildConfig.SITE_URL + "/offline", bundle.offlinePage() ?: offlineHtml(), "text/html", "utf-8", null)
                }
            }
        }

        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                // свой выбор файлов: все типы из accept (фото и видео сразу) и несколько файлов за раз
                val types = params.acceptTypes.flatMap { it.split(",") }.map { it.trim() }.filter { it.isNotEmpty() }
                val pick = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = if (types.size == 1) types[0] else "*/*"
                    if (types.size > 1) putExtra(Intent.EXTRA_MIME_TYPES, types.toTypedArray())
                    if (params.mode == FileChooserParams.MODE_OPEN_MULTIPLE) putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                return try {
                    fileChooser.launch(Intent.createChooser(pick, null))
                    true
                } catch (e: ActivityNotFoundException) {
                    fileCallback = null
                    false
                }
            }

            override fun onPermissionRequest(request: PermissionRequest) {
                if (!isOwn(request.origin)) {
                    request.deny()
                    return
                }
                runOnUiThread {
                    val needed = mutableListOf<String>()
                    if (request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE) && !has(Manifest.permission.RECORD_AUDIO)) {
                        needed.add(Manifest.permission.RECORD_AUDIO)
                    }
                    if (request.resources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE) && !has(Manifest.permission.CAMERA)) {
                        needed.add(Manifest.permission.CAMERA)
                    }
                    if (needed.isEmpty()) {
                        grantAllowed(request)
                    } else {
                        pendingPermission?.deny()
                        pendingPermission = request
                        mediaPermissions.launch(needed.toTypedArray())
                    }
                }
            }
        }

        web.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            try {
                val name = URLUtil.guessFileName(url, contentDisposition, mimeType)
                val req = DownloadManager.Request(Uri.parse(url))
                    .setMimeType(mimeType)
                    .addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url) ?: "")
                    .addRequestHeader("User-Agent", userAgent)
                    .setTitle(name)
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                if (Build.VERSION.SDK_INT >= 29) {
                    req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name)
                } else {
                    // Android 7–9: в общую папку нужно отдельное разрешение — сохраняем в папку приложения
                    req.setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, name)
                }
                (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(req)
                Toast.makeText(this, "Скачивание: $name", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                openExternal(Uri.parse(url))
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) {
                    web.goBack()
                } else {
                    moveTaskToBack(true)
                }
            }
        })

        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState)
        } else {
            web.loadUrl(startUrl(intent))
        }

        if (Build.VERSION.SDK_INT >= 33 && !has(Manifest.permission.POST_NOTIFICATIONS)) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else {
            NotifyService.start(this)
            askBatteryOnce()
        }
        NotifyWorker.schedule(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val data = intent.data
        if (data != null && isOwn(data)) web.loadUrl(data.toString())
        else safePath(intent.getStringExtra(NotifyWorker.EXTRA_PATH))?.let { web.loadUrl(it) }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    /** Один раз просим не «усыплять» приложение — иначе прошивка может остановить связь с сервером. */
    private fun askBatteryOnce() {
        if (Build.VERSION.SDK_INT < 23) return
        val prefs = getSharedPreferences("notify", MODE_PRIVATE)
        if (prefs.getBoolean("battery_asked", false)) return
        val pm = getSystemService(POWER_SERVICE) as PowerManager
        if (pm.isIgnoringBatteryOptimizations(packageName)) return
        prefs.edit().putBoolean("battery_asked", true).apply()
        try {
            @SuppressLint("BatteryLife")
            val i = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName"))
            startActivity(i)
        } catch (e: Exception) {
            // на некоторых прошивках такого экрана нет
        }
    }

    override fun onPause() {
        NotifyService.appVisible = false
        // приложение свёрнуто: сразу «не в сети» и без фоновой работы страницы
        web.evaluateJavascript("window.nuvoraOffline && window.nuvoraOffline()", null)
        web.onPause()
        super.onPause()
        CookieManager.getInstance().flush()
    }

    override fun onResume() {
        super.onResume()
        NotifyService.appVisible = true
        web.onResume()
    }

    private fun bundled(request: WebResourceRequest): WebResourceResponse? {
        if (request.method != "GET" || !isOwn(request.url)) return null
        return bundle.response(request.url)
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    /** Сеть пропала — берём страницы из кэша; вернулась — сами открываем сайт заново, если был офлайн-экран. */
    private fun watchNetwork() {
        val cm = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        try {
            cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    runOnUiThread {
                        web.settings.cacheMode = WebSettings.LOAD_DEFAULT
                        if (showingOffline) {
                            showingOffline = false
                            web.loadUrl(BuildConfig.SITE_URL)
                        }
                    }
                }

                override fun onLost(network: Network) {
                    runOnUiThread { if (!isOnline()) web.settings.cacheMode = WebSettings.LOAD_CACHE_ELSE_NETWORK }
                }
            })
        } catch (e: Exception) {
            // без доступа к состоянию сети приложение просто работает как раньше
        }
    }

    private fun startUrl(intent: Intent?): String {
        val data = intent?.data
        if (data != null && isOwn(data)) return data.toString()
        return safePath(intent?.getStringExtra(NotifyWorker.EXTRA_PATH)) ?: BuildConfig.SITE_URL
    }

    private fun isOwn(uri: Uri): Boolean {
        val host = uri.host ?: return false
        return uri.scheme == "https" && (host == BuildConfig.SITE_HOST || host == "www." + BuildConfig.SITE_HOST)
    }

    private fun isAuthHost(uri: Uri): Boolean {
        val host = uri.host ?: return false
        return uri.scheme == "https" && (host == "oauth.yandex.ru" || host == "passport.yandex.ru" || host == "id.yandex.ru" ||
            host == "sso.passport.yandex.ru" || host == "oauth.yandex.com" || host == "passport.yandex.com")
    }

    /** Путь из уведомления: только внутренний адрес сайта, без подмены хоста («@evil.com», «.evil.com»). */
    private fun safePath(path: String?): String? {
        if (path == null || !path.startsWith("/") || path.startsWith("//") || path.contains("\\")) return null
        val url = BuildConfig.SITE_URL + path
        return if (isOwn(Uri.parse(url))) url else null
    }

    private fun openExternal(uri: Uri) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "Не удалось открыть ссылку", Toast.LENGTH_SHORT).show()
        }
    }

    private fun has(permission: String) =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun grantAllowed(request: PermissionRequest) {
        val allowed = request.resources.filter {
            (it == PermissionRequest.RESOURCE_AUDIO_CAPTURE && has(Manifest.permission.RECORD_AUDIO)) ||
                (it == PermissionRequest.RESOURCE_VIDEO_CAPTURE && has(Manifest.permission.CAMERA))
        }
        if (allowed.isEmpty()) request.deny() else request.grant(allowed.toTypedArray())
    }

    /** Мост для сайта: тема (цвет полос под системными панелями) и сохранение картинок, созданных на странице. */
    inner class ThemeBridge {
        @JavascriptInterface
        fun setTheme(dark: Boolean, color: String?) {
            runOnUiThread { applyTheme(dark, color) }
        }

        @JavascriptInterface
        fun saveImage(base64: String, name: String): Boolean {
            return try {
                val bytes = Base64.decode(base64.substringAfter(","), Base64.DEFAULT)
                val file = name.replace(Regex("[^A-Za-z0-9._-]"), "_").ifEmpty { "nuvora.png" }
                if (Build.VERSION.SDK_INT >= 29) {
                    val values = ContentValues().apply {
                        put(MediaStore.Images.Media.DISPLAY_NAME, file)
                        put(MediaStore.Images.Media.MIME_TYPE, "image/png")
                        put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/Nuvora")
                    }
                    val uri = contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return false
                    contentResolver.openOutputStream(uri)?.use { it.write(bytes) } ?: return false
                } else {
                    val dir = getExternalFilesDir(Environment.DIRECTORY_PICTURES) ?: return false
                    java.io.File(dir, file).writeBytes(bytes)
                }
                runOnUiThread { Toast.makeText(this@MainActivity, "Картинка сохранена в «Галерею»", Toast.LENGTH_SHORT).show() }
                true
            } catch (e: Exception) {
                false
            }
        }
    }

    private fun applyTheme(dark: Boolean, color: String?) {
        var bg = if (dark) Color.parseColor("#09090B") else Color.parseColor("#FAFAFA")
        if (!color.isNullOrBlank()) {
            try {
                bg = Color.parseColor(color)
            } catch (e: IllegalArgumentException) {
                // неизвестный формат цвета — оставляем цвет по умолчанию
            }
        }
        root.setBackgroundColor(bg)
        window.decorView.setBackgroundColor(bg)
        WindowCompat.getInsetsController(window, root).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
    }

    private fun offlineHtml() = """
        <html><head><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"></head>
        <body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:90vh;margin:0;text-align:center;color:#71717a">
        <div><div style="font-size:48px">📡</div><h2 style="color:#18181b">Нет подключения</h2>
        <p>Проверьте интернет и попробуйте снова.</p>
        <button onclick="location.href='${BuildConfig.SITE_URL}'" style="background:#18181b;color:#fff;border:none;padding:12px 24px;border-radius:12px;font-size:16px">Повторить</button></div>
        </body></html>
    """.trimIndent()
}
