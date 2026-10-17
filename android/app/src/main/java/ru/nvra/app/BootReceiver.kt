package ru.nvra.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** После перезагрузки телефона или обновления приложения снова включаем мгновенные уведомления. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (context.getSharedPreferences("notify", Context.MODE_PRIVATE).getBoolean("live", true)) {
            NotifyService.start(context)
        }
        NotifyWorker.schedule(context)
    }
}
