package com.dashuai.gateway

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.content.ContentFactory
import java.awt.BorderLayout
import java.awt.Dimension
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration
import javax.swing.JButton
import javax.swing.JPanel
import javax.swing.JTextArea
import javax.swing.SwingUtilities

/**
 * Minimal sidebar chat: POST /v1/chat/completions with stream=false.
 */
class ChatToolWindowFactory : ToolWindowFactory, DumbAware {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = ChatPanel()
        val content = ContentFactory.getInstance().createContent(panel, "", false)
        toolWindow.contentManager.addContent(content)
    }
}

class ChatPanel : JPanel(BorderLayout(8, 8)) {
    private val output = JTextArea().apply {
        isEditable = false
        lineWrap = true
        wrapStyleWord = true
        text = "大帅问答 · 连接本机网关 /v1/chat/completions（非流式 MVP）\n"
    }
    private val input = JTextArea(3, 40).apply {
        lineWrap = true
        wrapStyleWord = true
    }
    private val sendBtn = JButton("发送")
    private val clearBtn = JButton("清空")
    private val client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build()

    init {
        border = javax.swing.BorderFactory.createEmptyBorder(8, 8, 8, 8)
        add(JBScrollPane(output), BorderLayout.CENTER)
        val bottom = JPanel(BorderLayout(6, 6))
        bottom.add(JBScrollPane(input).apply {
            preferredSize = Dimension(200, 72)
        }, BorderLayout.CENTER)
        val actions = JPanel()
        actions.add(clearBtn)
        actions.add(sendBtn)
        bottom.add(actions, BorderLayout.EAST)
        add(bottom, BorderLayout.SOUTH)

        clearBtn.addActionListener {
            output.text = ""
            input.text = ""
        }
        sendBtn.addActionListener { send() }
    }

    private fun send() {
        val prompt = input.text.trim()
        if (prompt.isEmpty()) return
        input.text = ""
        append("你：$prompt\n")
        sendBtn.isEnabled = false
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val reply = chatOnce(prompt)
                SwingUtilities.invokeLater {
                    append("大帅：$reply\n\n")
                    sendBtn.isEnabled = true
                }
            } catch (e: Exception) {
                SwingUtilities.invokeLater {
                    append("错误：${e.message ?: e}\n\n")
                    sendBtn.isEnabled = true
                }
            }
        }
    }

    private fun append(text: String) {
        output.append(text)
        output.caretPosition = output.document.length
    }

    private fun chatOnce(prompt: String): String {
        val s = DashuaiSettings.getInstance()
        val base = s.baseUrl.trimEnd('/')
        val url = if (base.endsWith("/v1")) "$base/chat/completions" else "$base/v1/chat/completions"
        val model = s.model.ifBlank { "日常" }
        val body = """
            {"model":${jsonStr(model)},"messages":[{"role":"user","content":${jsonStr(prompt)}}],"stream":false,"temperature":0.7}
        """.trimIndent()
        val req = HttpRequest.newBuilder()
            .uri(URI.create(url))
            .timeout(Duration.ofSeconds(120))
            .header("Authorization", "Bearer ${s.apiKey}")
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()
        val res = client.send(req, HttpResponse.BodyHandlers.ofString())
        if (res.statusCode() == 402) {
            throw RuntimeException("未激活或 Token 不足，请打开大帅网关控制台购买/激活")
        }
        if (res.statusCode() !in 200..299) {
            throw RuntimeException("HTTP ${res.statusCode()} ${res.body().take(300)}")
        }
        return extractContent(res.body())
    }

    private fun jsonStr(v: String): String {
        val escaped = v
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        return "\"$escaped\""
    }

    private fun extractContent(raw: String): String {
        // Minimal parse: "content":"..."
        val key = "\"content\""
        var idx = raw.indexOf(key)
        // Prefer message.content over other fields — take last occurrence near choices
        var last = -1
        while (idx >= 0) {
            last = idx
            idx = raw.indexOf(key, idx + key.length)
        }
        if (last < 0) return raw.take(500)
        val colon = raw.indexOf(':', last + key.length)
        if (colon < 0) return raw.take(500)
        var i = colon + 1
        while (i < raw.length && raw[i].isWhitespace()) i++
        if (i >= raw.length || raw[i] != '"') return raw.take(500)
        i++
        val sb = StringBuilder()
        while (i < raw.length) {
            val ch = raw[i]
            if (ch == '\\' && i + 1 < raw.length) {
                when (raw[i + 1]) {
                    'n' -> { sb.append('\n'); i += 2; continue }
                    'r' -> { sb.append('\r'); i += 2; continue }
                    't' -> { sb.append('\t'); i += 2; continue }
                    '"' -> { sb.append('"'); i += 2; continue }
                    '\\' -> { sb.append('\\'); i += 2; continue }
                    'u' -> {
                        if (i + 5 < raw.length) {
                            val hex = raw.substring(i + 2, i + 6)
                            sb.append(hex.toInt(16).toChar())
                            i += 6
                            continue
                        }
                    }
                }
            }
            if (ch == '"') break
            sb.append(ch)
            i++
        }
        return sb.toString().ifBlank { raw.take(500) }
    }
}
