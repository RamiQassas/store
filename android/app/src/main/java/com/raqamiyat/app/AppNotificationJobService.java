package com.raqamiyat.app;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.os.Build;

public class AppNotificationJobService extends JobService {

    private static final int JOB_ID = 9041;

    public static void scheduleBackgroundSync(Context context) {
        try {
            JobScheduler scheduler = (JobScheduler) context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
            if (scheduler == null) return;

            ComponentName comp = new ComponentName(context, AppNotificationJobService.class);
            JobInfo.Builder builder = new JobInfo.Builder(JOB_ID, comp)
                    .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                    .setMinimumLatency(45 * 1000L)
                    .setOverrideDeadline(120 * 1000L);

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder.setRequiresBatteryNotLow(false);
            }
            scheduler.schedule(builder.build());
        } catch (Exception ignored) {
        }
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        AppNotificationSync sync = new AppNotificationSync(getApplicationContext());
        sync.syncNow(items -> {
            scheduleBackgroundSync(getApplicationContext());
            jobFinished(params, false);
        });
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }
}
