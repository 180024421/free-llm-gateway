package com.dashuai.gateway

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.options.Configurable
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import javax.swing.JComponent
import javax.swing.JPanel

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
    private val apiKey = JBTextField()
    private val model = JBTextField()
    private val dashboard = JBTextField()
    private var panel: JPanel? = null

    override fun getDisplayName(): String = "大帅网关"

    override fun createComponent(): JComponent {
        val s = DashuaiSettings.getInstance()
        baseUrl.text = s.baseUrl
        apiKey.text = s.apiKey
        model.text = s.model
        dashboard.text = s.dashboardUrl
        panel = FormBuilder.createFormBuilder()
            .addLabeledComponent("Base URL", baseUrl, 1, false)
            .addLabeledComponent("API Key", apiKey, 1, false)
            .addLabeledComponent("Model", model, 1, false)
            .addLabeledComponent("控制台", dashboard, 1, false)
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
}
