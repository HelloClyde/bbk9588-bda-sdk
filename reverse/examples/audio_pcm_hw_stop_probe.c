#include "bda_audio.h"

#define C200_EMULATOR_AIC_RESET_VA 0x80195b24u

static void audio_pcm_stop_split_trace(void);

#define AUDIO_PCM_TRACE_START_TEXT \
    "START AUDIO PCM TRUE HARDWARE STOP TRACE V3"
#define AUDIO_PCM_TRACE_RETURN_TEXT \
    "RETURN AUDIO PCM TRUE HARDWARE STOP TRACE V3"
#define bda_audio_stop audio_pcm_stop_split_trace

#include "../../example/system/audio_pcm/audio_pcm_demo.c"

#undef bda_audio_stop

static void audio_pcm_stop_split_trace(void) {
    typedef void (*finish_fn_t)(void);
    typedef void (*aic_reset_fn_t)(u32);
    finish_fn_t finish_fn = (finish_fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_FINISH
    );
    aic_reset_fn_t reset_fn =
        (aic_reset_fn_t)C200_EMULATOR_AIC_RESET_VA;

    log_text("BEFORE SYS FINISH");
    finish_fn();
    log_text("AFTER SYS FINISH");
    log_text("BEFORE AIC RESET");
    reset_fn(0u);
    log_text("AFTER AIC RESET");
}
