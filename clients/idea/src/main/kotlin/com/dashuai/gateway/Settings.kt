package com.dashuai.gateway

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.options.Configurable
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.SwingUtilities

data class DashuaiState(
    var baseUrl: String = "http://127.0.0.1:8010/v1",
    var apiKey: String = "sk-local-change-me",
    var model: String = "daily",
    var dashboardUrl: String = "http://127.0.0.1:8010/ui/",
)

@State(name = "DashuaiGatewaySettings", storages = [Storage("DashuaiGateway.xml")])
class DashuaiSettings : PersistentStateComponent<DashuaiState> {
    private var state = DashuaiState()

    var baseUrl: String
        get() = state.baseUrl
        set(v) { state.baseUrl = v }

    var apiKey: String
        get() = state.apiKey
        set(v) { state.apiKey = v }

    var model: String
        get() = state.model
        set(v) { state.model = v }

    var dashboardUrl: String
        get() = state.dashboardUrl
        set(v) { state.dashboardUrl = v }

    override fun getState(): DashuaiState = state
    override fun loadState(state: DashuaiState) { this.state = state }

    companion object {
        fun getInstance(): DashuaiSettings =
            ApplicationManager.getApplication().getService(DashuaiSettings::class.java)
    }
}

class DashuaiConfigurable : Configurable {
    private val baseUrl = JBTextField()
    private val apiKey = JBPasswordField()
    private val model = JBTextField()
    private val dashboard = JBTextField()
    private val testButton = JButton("测试连接")
    private val testStatus = JBLabel("")
    private var panel: JPanel? = null

    override fun getDisplayName(): String = "大帅网关"

    override fun createComponent(): JComponent {
        val s = DashuaiSettings.getInstance()
        baseUrl.text = s.baseUrl
        apiKey.text = s.apiKey
        model.text = s.model
        dashboard.text = s.dashboardUrl
        testButton.addActionListener { testConnection() }
        val testRow = JPanel().apply {
            add(testButton)
            add(testStatus)
        }
        panel = FormBuilder.createFormBuilder()
            .addLabeledComponent("Base URL", baseUrl, 1, false)
            .addLabeledComponent("API Key", apiKey, 1, false)
            .addLabeledComponent("Model", model, 1, false)
            .addLabeledComponent("控制台", dashboard, 1, false)
            .addLabeledComponent("连接诊断", testRow, 1, false)
            .addComponentFillVertically(JPanel(), 0)
            .panel
        return panel!!
    }

    override fun isModified(): Boolean {
        val s = DashuaiSettings.getInstance()
        return baseUrl.text != s.baseUrl || apiKey.text != s.apiKey ||
            model.text != s.model || dashboard.text != s.dashboardUrl
    }

    override fun apply() {
        val s = DashuaiSettings.getInstance()
        s.baseUrl = baseUrl.text.trim()
        s.apiKey = apiKey.text.trim()
        s.model = model.text.trim()
        s.dashboardUrl = dashboard.text.trim()
    }

    override fun reset() {
        val s = DashuaiSettings.getInstance()
        baseUrl.text = s.baseUrl
        apiKey.text = s.apiKey
        model.text = s.model
        dashboard.text = s.dashboardUrl
    }

    private fun testConnection() {
        val base = baseUrl.text.trim().trimEnd('/').removeSuffix("/v1")
        val key = String(apiKey.password).trim()
        testButton.isEnabled = false
        testStatus.text = "检测中…"
        ApplicationManager.getApplication().executeOnPooledThread {
            val message = try {
                val request = HttpRequest.newBuilder()
                    .uri(URI.create("$base/api/diagnostics/connect"))
                    .timeout(Duration.ofSeconds(12))
                    .header("Authorization", "Bearer $key")
                    .GET()
                    .build()
                val response = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(8))
                    .build()
                    .send(request, HttpResponse.BodyHandlers.ofString())
                when (response.statusCode()) {
                    200 -> if (response.body().contains("\"ok\":true")) "连接正常" else "网关已连接，但尚未就绪，请打开控制台"
                    401 -> "API Key 不正确，请重新同步客户端"
                    402 -> "未激活或 Token 不足"
                    429 -> "请求过多，请稍后重试"
                    else -> "检测失败：HTTP ${response.statusCode()}"
                }
            } catch (e: Exception) {
                "无法连接网关：${e.message ?: "请确认网关已启动"}"
            }
            SwingUtilities.invokeLater {
                testStatus.text = message
                testButton.isEnabled = true
            }
        }
    }
}
