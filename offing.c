#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <errno.h>

#ifdef _WIN32
#  include <windows.h>
#  define PLATFORM_WINDOWS 1
#  define sleep_seconds(s) Sleep((DWORD)((s) * 1000))
#else
#  include <unistd.h>
#  define PLATFORM_WINDOWS 0
#  define sleep_seconds(s) sleep((unsigned int)(s))
#  ifdef __APPLE__
#    define PLATFORM_MACOS 1
#  else
#    define PLATFORM_MACOS 0
#  endif
#endif

#define TIME_FILE      "shutdown_time.txt"
#define EMAIL_FILE     "email_settings.txt"
#define MAX_LINE       512
#define POLL_INTERVAL  15
#define WARN_MINUTES   5
#define COUNTDOWN_SEC  5

typedef struct {
    int hour;
    int minute;
} ShutdownTime;

typedef struct {
    char sender[MAX_LINE];
    char app_password[MAX_LINE];
    char receiver[MAX_LINE];
} EmailConfig;

typedef enum {
    READ_OK = 0,
    READ_ERR_OPEN,
    READ_ERR_PARSE
} ReadResult;

static int clamp(int val, int lo, int hi) {
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

static void strip_newline(char *s) {
    if (!s) return;
    size_t len = strlen(s);
    while (len > 0 && (s[len - 1] == '\r' || s[len - 1] == '\n' || s[len - 1] == ' '))
        s[--len] = '\0';
}

static ReadResult read_shutdown_time(ShutdownTime *out) {
    if (!out) return READ_ERR_PARSE;

    FILE *f = fopen(TIME_FILE, "r");
    if (!f) return READ_ERR_OPEN;

    char line[MAX_LINE] = {0};
    if (!fgets(line, sizeof(line), f)) {
        fclose(f);
        return READ_ERR_PARSE;
    }
    fclose(f);

    strip_newline(line);

    int h = -1, m = -1;
    if (sscanf(line, "%d:%d", &h, &m) != 2) return READ_ERR_PARSE;
    if (h < 0 || h > 23 || m < 0 || m > 59) return READ_ERR_PARSE;

    out->hour   = h;
    out->minute = m;
    return READ_OK;
}

static ReadResult read_email_config(EmailConfig *out) {
    if (!out) return READ_ERR_PARSE;
    memset(out, 0, sizeof(EmailConfig));

    FILE *f = fopen(EMAIL_FILE, "r");
    if (!f) return READ_ERR_OPEN;

    char lines[3][MAX_LINE];
    memset(lines, 0, sizeof(lines));
    int i = 0;
    while (i < 3 && fgets(lines[i], MAX_LINE, f)) {
        strip_newline(lines[i]);
        i++;
    }
    fclose(f);

    if (i < 3) return READ_ERR_PARSE;
    if (strlen(lines[0]) == 0 || strlen(lines[1]) == 0 || strlen(lines[2]) == 0)
        return READ_ERR_PARSE;

    strncpy(out->sender,       lines[0], MAX_LINE - 1);
    strncpy(out->app_password, lines[1], MAX_LINE - 1);
    strncpy(out->receiver,     lines[2], MAX_LINE - 1);
    return READ_OK;
}

static void get_current_minutes(int *total_minutes_out) {
    time_t now = time(NULL);
    if (now == (time_t)-1) {
        *total_minutes_out = -1;
        return;
    }
    struct tm *lt = localtime(&now);
    if (!lt) {
        *total_minutes_out = -1;
        return;
    }
    *total_minutes_out = lt->tm_hour * 60 + lt->tm_min;
}

static void speak(const char *text) {
    if (!text) return;
    char cmd[MAX_LINE * 2];

#if PLATFORM_WINDOWS
    snprintf(cmd, sizeof(cmd),
        "powershell -NoProfile -WindowStyle Hidden -Command "
        "\"Add-Type -AssemblyName System.Speech; "
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('%s')\"",
        text);
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    memset(&pi, 0, sizeof(pi));
    if (CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 8000);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
#elif PLATFORM_MACOS
    snprintf(cmd, sizeof(cmd), "say \"%s\" 2>/dev/null &", text);
    (void)system(cmd);
#else
    snprintf(cmd, sizeof(cmd),
        "(espeak \"%s\" 2>/dev/null || "
        " festival --tts <<< \"%s\" 2>/dev/null || "
        " spd-say \"%s\" 2>/dev/null) &",
        text, text, text);
    (void)system(cmd);
#endif
}

static void send_email_alert(const EmailConfig *cfg, const char *subject, const char *body) {
    if (!cfg) return;

    char script_path[MAX_LINE];
    snprintf(script_path, sizeof(script_path), "email_send_tmp_%ld.py", (long)time(NULL));

    FILE *f = fopen(script_path, "w");
    if (!f) return;

    fprintf(f,
        "import smtplib, sys\n"
        "from email.mime.multipart import MIMEMultipart\n"
        "from email.mime.text import MIMEText\n"
        "try:\n"
        "    sender = '%s'\n"
        "    password = '%s'\n"
        "    receiver = '%s'\n"
        "    subject = '%s'\n"
        "    body = '%s'\n"
        "    msg = MIMEMultipart()\n"
        "    msg['From'] = sender\n"
        "    msg['To'] = receiver\n"
        "    msg['Subject'] = subject\n"
        "    msg.attach(MIMEText(body, 'plain'))\n"
        "    s = smtplib.SMTP('smtp.gmail.com', 587)\n"
        "    s.starttls()\n"
        "    s.login(sender, password)\n"
        "    s.send_message(msg)\n"
        "    s.quit()\n"
        "except Exception as e:\n"
        "    sys.stderr.write(str(e) + '\\n')\n",
        cfg->sender, cfg->app_password, cfg->receiver,
        subject ? subject : "", body ? body : "");
    fclose(f);

    char cmd[MAX_LINE * 4];
#if PLATFORM_WINDOWS
    snprintf(cmd, sizeof(cmd), "python \"%s\"", script_path);
#else
    snprintf(cmd, sizeof(cmd), "python3 \"%s\" 2>/dev/null", script_path);
#endif
    (void)system(cmd);
    remove(script_path);
}

static void do_shutdown(void) {
#if PLATFORM_WINDOWS
    (void)system("shutdown /s /t 0");
#elif PLATFORM_MACOS
    (void)system("sudo shutdown -h now");
#else
    (void)system("shutdown -h now");
#endif
}

static void emit_warning(const EmailConfig *cfg_or_null) {
    speak("Warning: your scheduled shutdown time is in five minutes. Please save your work.");
    if (cfg_or_null) {
        send_email_alert(
            cfg_or_null,
            "Warning: Scheduled Shutdown in 5 Minutes",
            "Your computer is scheduled to shut down in 5 minutes. "
            "Please save all open files and work before the deadline."
        );
    }
    sleep_seconds(5);
    speak("Reminder: shutdown in approximately five minutes. Save your work now.");
}

static void countdown_and_shutdown(const EmailConfig *cfg_or_null) {
    if (cfg_or_null) {
        send_email_alert(
            cfg_or_null,
            "Alert: System Shutting Down Now",
            "Your computer is shutting down now as scheduled."
        );
    }

    speak("System shutting down in five four three two one");
    for (int i = COUNTDOWN_SEC; i > 0; i--) {
        sleep_seconds(1);
    }
    do_shutdown();
}

int main(void) {
    ShutdownTime st;
    ReadResult res = read_shutdown_time(&st);
    if (res != READ_OK) {
        fprintf(stderr, "shutdown-guard: cannot read %s (error %d)\n", TIME_FILE, (int)res);
        return EXIT_FAILURE;
    }

    int target_total = st.hour * 60 + st.minute;

    sleep_seconds(POLL_INTERVAL);

    int warned = 0;
    int max_iterations = 24 * 60;
    int iteration = 0;

    while (iteration++ < max_iterations) {
        int current_total = -1;
        get_current_minutes(&current_total);
        if (current_total < 0) {
            sleep_seconds(POLL_INTERVAL);
            continue;
        }

        int diff = target_total - current_total;

        if (diff == 0) {
            EmailConfig cfg;
            EmailConfig *cfg_ptr = NULL;
            if (read_email_config(&cfg) == READ_OK) cfg_ptr = &cfg;
            countdown_and_shutdown(cfg_ptr);
            break;
        }

        if (!warned && diff == WARN_MINUTES) {
            warned = 1;
            EmailConfig cfg;
            EmailConfig *cfg_ptr = NULL;
            if (read_email_config(&cfg) == READ_OK) cfg_ptr = &cfg;
            emit_warning(cfg_ptr);
            sleep_seconds(POLL_INTERVAL);
            continue;
        }

        if (diff < 0 && diff > -2) {
            EmailConfig cfg;
            EmailConfig *cfg_ptr = NULL;
            if (read_email_config(&cfg) == READ_OK) cfg_ptr = &cfg;
            countdown_and_shutdown(cfg_ptr);
            break;
        }

        sleep_seconds(POLL_INTERVAL);
    }

    return EXIT_SUCCESS;
}
