#include "bda_audio.h"

static void audio_pcm_finish_only_trace(void);

#define AUDIO_PCM_TRACE_START_TEXT \
    "START AUDIO PCM TRUE HARDWARE FINISH TRACE V4"
#define AUDIO_PCM_TRACE_RETURN_TEXT \
    "RETURN AUDIO PCM TRUE HARDWARE FINISH TRACE V4"
#define bda_audio_stop audio_pcm_finish_only_trace

#include "../../example/system/audio_pcm/audio_pcm_demo.c"

#undef bda_audio_stop

static void audio_pcm_finish_only_trace(void) {
    typedef void (*finish_fn_t)(void);
    finish_fn_t finish_fn = (finish_fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_FINISH
    );

    log_text("BEFORE SYS FINISH ONLY");
    finish_fn();
    log_text("AFTER SYS FINISH ONLY");
}
