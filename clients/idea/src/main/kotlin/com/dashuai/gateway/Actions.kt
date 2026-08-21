package com.dashuai.gateway

import com.intellij.ide.BrowserUtil
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages

class OpenDashboardAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val url = DashuaiSettings.getInstance().dashboardUrl
        BrowserUtil.browse(url)
    }
}

class ShowConnectHintAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val s = DashuaiSettings.getInstance()
        Messages.showInfoMessage(
            """
            Base URL: ${s.baseUrl}
            API Key : ${s.apiKey}
            Model   : ${s.model}

            在支持 OpenAI 兼容的插件里填入以上信息即可。
            """.trimIndent(),
            "大帅网关接入说明"
        )
    }
}
