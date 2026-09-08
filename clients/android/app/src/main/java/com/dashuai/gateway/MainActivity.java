package com.dashuai.gateway;

import android.annotation.SuppressLint;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.activity.result.ActivityResultLauncher;
import androidx.appcompat.app.AppCompatActivity;

import com.journeyapps.barcodescanner.ScanContract;
import com.journeyapps.barcodescanner.ScanOptions;

import org.json.JSONObject;

public class MainActivity extends AppCompatActivity {
    private WebView webView;
    private final ActivityResultLauncher<ScanOptions> qrScanner =
        registerForActivityResult(new ScanContract(), result -> {
            if (result.getContents() == null) {
                return;
            }
            String value = JSONObject.quote(result.getContents());
            webView.evaluateJavascript("window.onDashuaiPairingCode(" + value + ")", null);
        });

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new NativeBridge(), "DashuaiNative");
        webView.loadUrl("file:///android_asset/www/index.html");
    }

    private final class NativeBridge {
        @JavascriptInterface
        public void scanPairingCode() {
            runOnUiThread(() -> {
                ScanOptions options = new ScanOptions();
                options.setPrompt("扫描大帅网关控制台中的连接二维码");
                options.setBeepEnabled(false);
                options.setOrientationLocked(false);
                options.setDesiredBarcodeFormats(ScanOptions.QR_CODE);
                qrScanner.launch(options);
            });
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
