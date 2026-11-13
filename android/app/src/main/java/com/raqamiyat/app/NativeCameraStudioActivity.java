package com.raqamiyat.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.Camera;
import androidx.camera.core.CameraSelector;
import androidx.camera.core.ImageCapture;
import androidx.camera.core.ImageCaptureException;
import androidx.camera.core.ImageProxy;
import androidx.camera.core.Preview;
import androidx.camera.lifecycle.ProcessCameraProvider;
import androidx.camera.view.PreviewView;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.bumptech.glide.Glide;
import com.bumptech.glide.load.engine.DiskCacheStrategy;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmentation;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmenter;
import com.google.mlkit.vision.segmentation.subject.SubjectSegmenterOptions;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class NativeCameraStudioActivity extends AppCompatActivity {

    private static final String DOMAIN = "https://raqamiyatapp.com";
    private static final String LOOKUP_URL = DOMAIN + "/api/studio/lookup-product/?code=";
    private static final String PROCESS_URL = DOMAIN + "/control/camera-studio/process-ajax/";
    private static final int CAMERA_PERMISSION_CODE = 3001;
    private static final int GALLERY_REQUEST_CODE = 3002;

    private LinearLayout codeEntryStage;
    private RelativeLayout cameraStage;
    private LinearLayout processingStage;
    private LinearLayout resultStage;

    private EditText inputProductCode;
    private TextView codeErrorText;
    private ProgressBar codeLookupProgress;
    private Button btnLookupCode;
    private Button btnChangeCode;
    private TextView activeProductLabel;
    private TextView processingLabel;

    private PreviewView cameraPreview;
    private TextView optBgWhite;
    private TextView optBgDark;
    private Button btnFlash;
    private ImageView resultPreviewImage;
    private TextView resultStatusTitle;

    private String activeProductId = "";
    private String activeProductName = "";
    private String activeProductCode = "";
    private String selectedBgStyle = "studio_white";
    private boolean flashEnabled = false;

    private ImageCapture imageCapture;
    private Camera boundCamera;
    private final ExecutorService executor = Executors.newFixedThreadPool(2);
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            getWindow().setStatusBarColor(0xFF030712);
            getWindow().setNavigationBarColor(0xFF030712);
        }
        setContentView(R.layout.activity_native_camera_studio);

        bindViews();
        setupListeners();
        showCodeEntryStage();
    }

    private void bindViews() {
        codeEntryStage = findViewById(R.id.code_entry_stage);
        cameraStage = findViewById(R.id.camera_stage);
        processingStage = findViewById(R.id.processing_stage);
        resultStage = findViewById(R.id.result_stage);

        inputProductCode = findViewById(R.id.input_product_code);
        codeErrorText = findViewById(R.id.code_error_text);
        codeLookupProgress = findViewById(R.id.code_lookup_progress);
        btnLookupCode = findViewById(R.id.btn_lookup_code);
        btnChangeCode = findViewById(R.id.btn_change_code);
        activeProductLabel = findViewById(R.id.studio_active_product_label);
        processingLabel = findViewById(R.id.processing_label);

        cameraPreview = findViewById(R.id.camera_preview);
        optBgWhite = findViewById(R.id.opt_bg_white);
        optBgDark = findViewById(R.id.opt_bg_dark);
        btnFlash = findViewById(R.id.btn_studio_flash);
        resultPreviewImage = findViewById(R.id.result_preview_image);
        resultStatusTitle = findViewById(R.id.result_status_title);
    }

    private void setupListeners() {
        ImageButton btnClose = findViewById(R.id.btn_studio_close);
        btnClose.setOnClickListener(v -> finish());

        btnLookupCode.setOnClickListener(v -> lookupProductByCode());
        inputProductCode.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_GO ||
                    (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER && event.getAction() == KeyEvent.ACTION_DOWN)) {
                lookupProductByCode();
                return true;
            }
            return false;
        });

        btnChangeCode.setOnClickListener(v -> showCodeEntryStage());

        optBgWhite.setOnClickListener(v -> {
            selectedBgStyle = "studio_white";
            optBgWhite.setBackgroundResource(R.drawable.bg_chip_selected);
            optBgWhite.setTextColor(0xFF030712);
            optBgDark.setBackgroundResource(0);
            optBgDark.setTextColor(0xFFE2E8F0);
        });

        optBgDark.setOnClickListener(v -> {
            selectedBgStyle = "studio_dark";
            optBgDark.setBackgroundResource(R.drawable.bg_chip_selected);
            optBgDark.setTextColor(0xFF030712);
            optBgWhite.setBackgroundResource(0);
            optBgWhite.setTextColor(0xFFE2E8F0);
        });

        Button btnCapture = findViewById(R.id.btn_studio_capture);
        btnCapture.setOnClickListener(v -> captureFromCamera());

        Button btnGallery = findViewById(R.id.btn_studio_gallery);
        btnGallery.setOnClickListener(v -> {
            Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
            intent.setType("image/*");
            startActivityForResult(Intent.createChooser(intent, "اختر صورة المنتج"), GALLERY_REQUEST_CODE);
        });

        btnFlash.setOnClickListener(v -> {
            flashEnabled = !flashEnabled;
            btnFlash.setText(flashEnabled ? "فلاش: تشغيل" : "فلاش: إيقاف");
            if (imageCapture != null) {
                imageCapture.setFlashMode(flashEnabled ? ImageCapture.FLASH_MODE_ON : ImageCapture.FLASH_MODE_OFF);
            }
            if (boundCamera != null && boundCamera.getCameraInfo().hasFlashUnit()) {
                boundCamera.getCameraControl().enableTorch(flashEnabled);
            }
        });

        Button btnNext = findViewById(R.id.btn_next_product);
        btnNext.setOnClickListener(v -> {
            inputProductCode.setText("");
            showCodeEntryStage();
        });

        Button btnRetake = findViewById(R.id.btn_retake_current);
        btnRetake.setOnClickListener(v -> showCameraStage());

        Button btnDone = findViewById(R.id.btn_done_studio);
        btnDone.setOnClickListener(v -> finish());
    }

    private void showCodeEntryStage() {
        codeEntryStage.setVisibility(View.VISIBLE);
        cameraStage.setVisibility(View.GONE);
        processingStage.setVisibility(View.GONE);
        resultStage.setVisibility(View.GONE);
        btnChangeCode.setVisibility(View.GONE);
        codeErrorText.setVisibility(View.GONE);
        activeProductLabel.setText("أدخل كود المنتج للبدء");
        inputProductCode.requestFocus();
    }

    private void showCameraStage() {
        hideKeyboard();
        codeEntryStage.setVisibility(View.GONE);
        processingStage.setVisibility(View.GONE);
        resultStage.setVisibility(View.GONE);
        cameraStage.setVisibility(View.VISIBLE);
        btnChangeCode.setVisibility(View.VISIBLE);

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION_CODE);
        } else {
            startCamera();
        }
    }

    private void hideKeyboard() {
        try {
            InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
            if (imm != null && getCurrentFocus() != null) {
                imm.hideSoftInputFromWindow(getCurrentFocus().getWindowToken(), 0);
            }
        } catch (Exception ignored) {
        }
    }

    private void lookupProductByCode() {
        String code = inputProductCode.getText() != null ? inputProductCode.getText().toString().trim() : "";
        if (code.isEmpty()) {
            codeErrorText.setText("يرجى إدخال كود المنتج أولاً");
            codeErrorText.setVisibility(View.VISIBLE);
            return;
        }

        codeErrorText.setVisibility(View.GONE);
        codeLookupProgress.setVisibility(View.VISIBLE);
        btnLookupCode.setEnabled(false);

        executor.execute(() -> {
            try {
                String urlStr = LOOKUP_URL + URLEncoder.encode(code, "UTF-8");
                HttpURLConnection conn = (HttpURLConnection) new URL(urlStr).openConnection();
                conn.setConnectTimeout(7000);
                conn.setReadTimeout(8000);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 Studio");
                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                }
                conn.connect();

                int status = conn.getResponseCode();
                InputStream is = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                String body = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                sc.close();

                JSONObject json = new JSONObject(body);
                if (status == 200 && "success".equals(json.optString("status"))) {
                    JSONObject prod = json.getJSONObject("product");
                    String pId = prod.optString("id");
                    String pName = prod.optString("name");
                    String pCode = prod.optString("code", code);

                    mainHandler.post(() -> {
                        codeLookupProgress.setVisibility(View.GONE);
                        btnLookupCode.setEnabled(true);
                        activeProductId = pId;
                        activeProductName = pName;
                        activeProductCode = pCode;
                        activeProductLabel.setText(pName + " • كود: " + pCode);
                        showCameraStage();
                    });
                    return;
                }

                String errMsg = json.optString("message", "لم يتم العثور على المنتج أو يرجى تسجيل الدخول كإدارة");
                mainHandler.post(() -> {
                    codeLookupProgress.setVisibility(View.GONE);
                    btnLookupCode.setEnabled(true);
                    codeErrorText.setText(errMsg);
                    codeErrorText.setVisibility(View.VISIBLE);
                });
            } catch (Exception e) {
                mainHandler.post(() -> {
                    codeLookupProgress.setVisibility(View.GONE);
                    btnLookupCode.setEnabled(true);
                    codeErrorText.setText("تعذر الاتصال بالخادم، تأكد من الإنترنت وصلاحية الإدارة");
                    codeErrorText.setVisibility(View.VISIBLE);
                });
            }
        });
    }

    private void startCamera() {
        ListenableFuture<ProcessCameraProvider> cameraProviderFuture = ProcessCameraProvider.getInstance(this);
        cameraProviderFuture.addListener(() -> {
            try {
                ProcessCameraProvider cameraProvider = cameraProviderFuture.get();
                Preview preview = new Preview.Builder().build();
                preview.setSurfaceProvider(cameraPreview.getSurfaceProvider());

                imageCapture = new ImageCapture.Builder()
                        .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                        .setFlashMode(flashEnabled ? ImageCapture.FLASH_MODE_ON : ImageCapture.FLASH_MODE_OFF)
                        .build();

                CameraSelector cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA;
                cameraProvider.unbindAll();
                boundCamera = cameraProvider.bindToLifecycle(this, cameraSelector, preview, imageCapture);
            } catch (Exception e) {
                Toast.makeText(this, "تعذر تشغيل الكاميرا: " + e.getMessage(), Toast.LENGTH_SHORT).show();
            }
        }, ContextCompat.getMainExecutor(this));
    }

    private void captureFromCamera() {
        if (imageCapture == null) {
            Toast.makeText(this, "الكاميرا غير جاهزة بعد", Toast.LENGTH_SHORT).show();
            return;
        }
        cameraStage.setVisibility(View.GONE);
        processingStage.setVisibility(View.VISIBLE);
        processingLabel.setText("جاري التقاط الصورة وعزل الخلفية باحترافية...");

        imageCapture.takePicture(ContextCompat.getMainExecutor(this), new ImageCapture.OnImageCapturedCallback() {
            @Override
            public void onCaptureSuccess(@NonNull ImageProxy image) {
                Bitmap bitmap = imageProxyToBitmap(image);
                image.close();
                if (bitmap != null) {
                    processBitmapWithBackgroundRemoval(bitmap);
                } else {
                    Toast.makeText(NativeCameraStudioActivity.this, "تعذر قراءة الصورة", Toast.LENGTH_SHORT).show();
                    showCameraStage();
                }
            }

            @Override
            public void onError(@NonNull ImageCaptureException exception) {
                Toast.makeText(NativeCameraStudioActivity.this, "فشل الالتقاط: " + exception.getMessage(), Toast.LENGTH_SHORT).show();
                showCameraStage();
            }
        });
    }

    private Bitmap imageProxyToBitmap(ImageProxy image) {
        try {
            ByteBuffer buffer = image.getPlanes()[0].getBuffer();
            byte[] bytes = new byte[buffer.remaining()];
            buffer.get(bytes);
            Bitmap raw = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (raw == null) return null;
            int rotation = image.getImageInfo().getRotationDegrees();
            if (rotation != 0) {
                Matrix matrix = new Matrix();
                matrix.postRotate(rotation);
                raw = Bitmap.createBitmap(raw, 0, 0, raw.getWidth(), raw.getHeight(), matrix, true);
            }
            return scaleDownAndCropSquare(raw, 1024);
        } catch (Exception e) {
            return null;
        }
    }

    private Bitmap scaleDownAndCropSquare(Bitmap src, int maxDim) {
        int w = src.getWidth();
        int h = src.getHeight();
        int size = Math.min(w, h);
        int x = (w - size) / 2;
        int y = (h - size) / 2;
        Bitmap square = Bitmap.createBitmap(src, x, y, size, size);
        if (size > maxDim) {
            return Bitmap.createScaledBitmap(square, maxDim, maxDim, true);
        }
        return square;
    }

    private void processBitmapWithBackgroundRemoval(Bitmap bitmap) {
        processingLabel.setText("جاري عزل الخلفية وإضافة خلفية وشعار رقميات...");
        try {
            SubjectSegmenterOptions options = new SubjectSegmenterOptions.Builder()
                    .enableForegroundBitmap()
                    .build();
            SubjectSegmenter segmenter = SubjectSegmentation.getClient(options);
            InputImage inputImage = InputImage.fromBitmap(bitmap, 0);

            segmenter.process(inputImage)
                    .addOnSuccessListener(result -> {
                        Bitmap fg = result.getForegroundBitmap();
                        if (fg != null) {
                            uploadProcessedImage(fg, true);
                        } else {
                            uploadProcessedImage(bitmap, false);
                        }
                    })
                    .addOnFailureListener(e -> {
                        // Fallback: server-side smart background removal in studio_camera.py
                        uploadProcessedImage(bitmap, false);
                    });
        } catch (Exception e) {
            uploadProcessedImage(bitmap, false);
        }
    }

    private void uploadProcessedImage(Bitmap bitmap, boolean isPngCutout) {
        executor.execute(() -> {
            try {
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                bitmap.compress(isPngCutout ? Bitmap.CompressFormat.PNG : Bitmap.CompressFormat.JPEG,
                        isPngCutout ? 100 : 90, baos);
                byte[] imgBytes = baos.toByteArray();

                String boundary = "----RaqamiyatStudio" + System.currentTimeMillis();
                HttpURLConnection conn = (HttpURLConnection) new URL(PROCESS_URL).openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(25000);
                conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                conn.setRequestProperty("User-Agent", "RaqamiyatAndroid/3.0 Studio");

                String cookies = CookieManager.getInstance().getCookie(DOMAIN);
                if (cookies != null && !cookies.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookies);
                    String csrf = extractCookie(cookies, "csrftoken");
                    if (!csrf.isEmpty()) {
                        conn.setRequestProperty("X-CSRFToken", csrf);
                    }
                }

                DataOutputStream dos = new DataOutputStream(conn.getOutputStream());
                writeFormField(dos, boundary, "product_id", activeProductId);
                writeFormField(dos, boundary, "isolate_white", "true");
                writeFormField(dos, boundary, "add_hallmark", "true");
                writeFormField(dos, boundary, "bg_style", selectedBgStyle);

                String fileName = isPngCutout ? "studio_cutout.png" : "studio_raw.jpg";
                String mimeType = isPngCutout ? "image/png" : "image/jpeg";
                dos.writeBytes("--" + boundary + "\r\n");
                dos.writeBytes("Content-Disposition: form-data; name=\"image\"; filename=\"" + fileName + "\"\r\n");
                dos.writeBytes("Content-Type: " + mimeType + "\r\n\r\n");
                dos.write(imgBytes);
                dos.writeBytes("\r\n--" + boundary + "--\r\n");
                dos.flush();
                dos.close();

                int status = conn.getResponseCode();
                InputStream is = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                Scanner sc = new Scanner(is, StandardCharsets.UTF_8.name());
                String respBody = sc.useDelimiter("\\A").hasNext() ? sc.next() : "";
                sc.close();

                JSONObject json = new JSONObject(respBody);
                if (status == 200 && "success".equals(json.optString("status"))) {
                    String finalUrl = CatalogRepository.resolveUrl(json.optString("image_url"));
                    mainHandler.post(() -> {
                        setResult(RESULT_OK);
                        processingStage.setVisibility(View.GONE);
                        resultStage.setVisibility(View.VISIBLE);
                        resultStatusTitle.setText("✓ تم تعيين صورة الاستوديو للمنتج: " + activeProductName);
                        Glide.with(NativeCameraStudioActivity.this)
                                .load(finalUrl)
                                .diskCacheStrategy(DiskCacheStrategy.NONE)
                                .skipMemoryCache(true)
                                .into(resultPreviewImage);
                    });
                    return;
                }

                String errMsg = json.optString("message", "فشل حفظ الصورة");
                mainHandler.post(() -> {
                    Toast.makeText(NativeCameraStudioActivity.this, errMsg, Toast.LENGTH_LONG).show();
                    showCameraStage();
                });
            } catch (Exception e) {
                mainHandler.post(() -> {
                    Toast.makeText(NativeCameraStudioActivity.this, "خطأ في الرفع: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    showCameraStage();
                });
            }
        });
    }

    private void writeFormField(DataOutputStream dos, String boundary, String name, String value) throws Exception {
        dos.writeBytes("--" + boundary + "\r\n");
        dos.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
        dos.write(value.getBytes(StandardCharsets.UTF_8));
        dos.writeBytes("\r\n");
    }

    private String extractCookie(String cookieHeader, String key) {
        String[] parts = cookieHeader.split(";");
        for (String part : parts) {
            String trimmed = part.trim();
            if (trimmed.startsWith(key + "=")) {
                return trimmed.substring(key.length() + 1);
            }
        }
        return "";
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == GALLERY_REQUEST_CODE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            cameraStage.setVisibility(View.GONE);
            processingStage.setVisibility(View.VISIBLE);
            executor.execute(() -> {
                try {
                    InputStream is = getContentResolver().openInputStream(uri);
                    Bitmap bmp = BitmapFactory.decodeStream(is);
                    if (is != null) is.close();
                    if (bmp != null) {
                        Bitmap squared = scaleDownAndCropSquare(bmp, 1024);
                        mainHandler.post(() -> processBitmapWithBackgroundRemoval(squared));
                    } else {
                        mainHandler.post(this::showCameraStage);
                    }
                } catch (Exception e) {
                    mainHandler.post(this::showCameraStage);
                }
            });
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == CAMERA_PERMISSION_CODE) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                startCamera();
            } else {
                Toast.makeText(this, "صلاحية الكاميرا مطلوبة لتصوير المنتجات", Toast.LENGTH_LONG).show();
            }
        }
    }
}
