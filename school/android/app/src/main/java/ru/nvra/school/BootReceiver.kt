package ru.nvra.school

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** После перезагрузки телефона или обновления приложения снова включаем проверку новых оценок и сообщений. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        NotifyWorker.schedule(context)
    }
}
