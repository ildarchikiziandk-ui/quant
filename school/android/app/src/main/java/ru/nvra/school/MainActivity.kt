package ru.nvra.school

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat

/** Приложение школы: сайт school.nvra.ru внутри приложения, уведомления и обновления без GitHub. */
class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private val updater by lazy { Updater(this) }
    private var offline = false

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        val root = FrameLayout(this)
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)
        // сайт не залезает под строку состояния, панель навигации и клавиатуру
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            WindowInsetsCompat.CONSUMED
        }

        CookieManager.getInstance().setAcceptCookie(true)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            setSupportZoom(false)
            userAgentString = "$userAgentString SchoolApp/${BuildConfig.VERSION_NAME}"
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (uri.host == BuildConfig.SITE_HOST && uri.path?.endsWith(".apk") != true) return false
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, uri))  // чужие ссылки и скачивание APK — в браузере
                } catch (e: ActivityNotFoundException) {
                }
                return true
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) showOffline()
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()  // вход сохраняется, даже если приложение закрыли сразу
            }
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack() && !offline) web.goBack() else finish()
            }
        })

        load(intent)
        NotifyWorker.schedule(this)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        updater.check()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        load(intent)
    }

    override fun onResume() {
        super.onResume()
        updater.resume()
        if (offline && isOnline()) load(null)
    }

    override fun onPause() {
        super.onPause()
        CookieManager.getInstance().flush()
    }

    private fun load(intent: Intent?) {
        offline = false
        // из уведомления — сразу на нужную страницу (/s/grades, /s/chat…)
        val path = intent?.getStringExtra(NotifyWorker.EXTRA_PATH)
        val link = intent?.data?.takeIf { it.host == BuildConfig.SITE_HOST }
        web.loadUrl(link?.toString() ?: (BuildConfig.SITE_URL + (path?.takeIf { it.startsWith("/") } ?: "/")))
    }

    private fun showOffline() {
        offline = true
        val html = """<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1">
            <body style="font-family:sans-serif;background:#f3f6fb;color:#17202c;display:flex;align-items:center;justify-content:center;height:90vh;text-align:center;margin:0">
            <div><div style="font-size:54px">📒</div><h2>Нет связи</h2><p style="color:#5b6678">Проверьте интернет — дневник откроется сам.</p>
            <button onclick="location.href='${BuildConfig.SITE_URL}/'" style="padding:12px 22px;border:0;border-radius:12px;background:#1f6fb8;color:#fff;font-size:16px">Повторить</button></div></body></html>"""
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null)
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java) ?: return true
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
