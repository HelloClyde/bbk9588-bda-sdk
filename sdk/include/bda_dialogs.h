#ifndef BDA_DIALOGS_H
#define BDA_DIALOGS_H

#include "bda_memory.h"
#include "bda/detail/runtime.h"

/* Dynamically verified GUI+0x2b8 modal layouts. */
#define BDA_MSGBOX_TYPE_OK          0u
#define BDA_MSGBOX_TYPE_YES_NO      2u
#define BDA_MSGBOX_TYPE_YES_ALL_NO  6u

#define BDA_DIALOG_RESULT_YES 6
#define BDA_DIALOG_RESULT_NO  7
#define BDA_DIALOG_RESULT_ALL 10

#define BDA_HELP_PAGE_TITLE_MAX_BYTES 27u
#define BDA_HELP_PAGE_ERROR            0
#define BDA_HELP_PAGE_COMPLETED        1

#define BDA_FILE_SELECTOR_PATH_SIZE            0x12du
#define BDA_FILE_SELECTOR_DIRECTORY_STATE_SIZE 0x12du
#define BDA_FILE_SELECTOR_ERROR                (-1)
#define BDA_FILE_SELECTOR_CANCELLED             0
#define BDA_FILE_SELECTOR_SELECTED              1

typedef struct bda_file_selector {
    char path[BDA_FILE_SELECTOR_PATH_SIZE];
    u8 directory_state[BDA_FILE_SELECTOR_DIRECTORY_STATE_SIZE];
} bda_file_selector_t;

/* Private file-selector implementation details. */
typedef struct bda_dialogs_internal_file_selector_desc {
    char *path;
    const char *extensions;
    void *directory_state;
    const char *title;
    void *list_head;
    u32 internal14;
    s32 status;
    s32 selected_index;
    s32 sentinel20;
    s32 sentinel24;
    u32 internal28;
    u32 internal2c;
    u32 flags;
    s32 sentinel34;
    s32 sentinel38;
    u32 internal3c;
    u32 list_limit40;
    u32 internal44;
    s32 sentinel48;
    u32 internal4c;
    u32 internal50;
    u32 internal54;
    u32 internal58;
    u32 internal5c;
    u32 internal60;
    u32 result64;
} bda_dialogs_internal_file_selector_desc_t;

#define BDA_DIALOGS_INTERNAL_GUI_FILE_SELECTOR_OPEN 0x6a8u
#define BDA_DIALOGS_INTERNAL_GUI_LIST_NTH           0x6b8u
#define BDA_DIALOGS_INTERNAL_GUI_LIST_FREE          0x6bcu
#define BDA_DIALOGS_INTERNAL_GUI_FILE_SELECTOR_RUN  0x6c8u
#define BDA_DIALOGS_INTERNAL_GUI_HELP_PAGE           0x5a8u

/* The firmware ABI uses parent,message,title,flags order. */
static inline int bda_msgbox_ex(
    void *parent, const char *title, const char *message, u32 flags
) {
    typedef int (*fn_t)(void *, const char *, const char *, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_MSGBOX
    );
    return fn(parent, message, title, flags);
}

static inline int bda_msgbox(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, BDA_MSGBOX_TYPE_OK);
}

static inline int bda_confirm(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, BDA_MSGBOX_TYPE_YES_NO);
}

static inline int bda_confirm_yes_all_no(
    const char *title, const char *message
) {
    return bda_msgbox_ex(0, title, message, BDA_MSGBOX_TYPE_YES_ALL_NO);
}

static inline int bda_dialogs_internal_copy_string(
    char *destination, bda_size_t capacity, const char *source
) {
    bda_size_t index;

    if (destination == 0 || capacity == 0u || source == 0) {
        return 0;
    }
    for (index = 0u; index < capacity; ++index) {
        destination[index] = source[index];
        if (source[index] == '\0') {
            return 1;
        }
    }
    destination[0] = '\0';
    return 0;
}

/*
 * Show the firmware's synchronous help page. This creates the temporary
 * "title\r\nbody" document required by GUI+0x5a8 and frees it after the
 * modal page closes. It does not add a question-mark button to the parent.
 */
static inline int bda_help_page(
    void *parent, const char *title, const char *body
) {
    typedef void (*fn_t)(void *, const char *);
    bda_size_t title_length = 0u;
    bda_size_t body_length = 0u;
    bda_size_t document_size;
    char *document;
    fn_t fn;

    if (title == 0 || body == 0) {
        return BDA_HELP_PAGE_ERROR;
    }
    while (title[title_length] != '\0') {
        if (title[title_length] == '\r' || title[title_length] == '\n' ||
            title_length >= BDA_HELP_PAGE_TITLE_MAX_BYTES) {
            return BDA_HELP_PAGE_ERROR;
        }
        ++title_length;
    }
    while (body[body_length] != '\0') {
        ++body_length;
    }
    if (body_length > 0xffffffffu - title_length - 3u) {
        return BDA_HELP_PAGE_ERROR;
    }

    document_size = title_length + 2u + body_length + 1u;
    document = (char *)bda_alloc(document_size);
    if (document == 0) {
        return BDA_HELP_PAGE_ERROR;
    }
    (void)bda_memcpy(document, title, title_length);
    document[title_length] = '\r';
    document[title_length + 1u] = '\n';
    (void)bda_memcpy(
        document + title_length + 2u, body, body_length + 1u
    );

    fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_DIALOGS_INTERNAL_GUI_HELP_PAGE
    );
    fn(parent, document);
    bda_free(document);
    return BDA_HELP_PAGE_COMPLETED;
}

static inline int bda_dialogs_internal_join_path(
    char *directory, bda_size_t capacity, const char *name
) {
    bda_size_t length = 0u;

    if (directory == 0 || capacity == 0u || name == 0 || name[0] == '\0') {
        return 0;
    }
    if (name[0] == '\\' || name[0] == '/' || name[1] == ':') {
        return bda_dialogs_internal_copy_string(directory, capacity, name);
    }
    while (length < capacity && directory[length] != '\0') {
        ++length;
    }
    if (length == capacity) {
        directory[0] = '\0';
        return 0;
    }
    if (length != 0u && directory[length - 1u] != '\\' &&
        directory[length - 1u] != '/') {
        if (length + 1u >= capacity) {
            directory[0] = '\0';
            return 0;
        }
        directory[length++] = '\\';
        directory[length] = '\0';
    }
    return bda_dialogs_internal_copy_string(
        directory + length, capacity - length, name
    );
}

/*
 * Run the firmware's synchronous modal file selector.
 *
 * default_path is normally an absolute directory ending in '\\', for example
 * "A:\\gameboy\\". extensions is a semicolon-separated list without dots,
 * for example "gb;gbc". The selected absolute path is copied into selector.
 */
static inline int bda_gui_select_file(
    bda_file_selector_t *selector,
    const char *default_path,
    const char *extensions,
    const char *title
) {
    bda_dialogs_internal_file_selector_desc_t descriptor;
    void *selected_node;
    const char *selected_path;
    int result = BDA_FILE_SELECTOR_CANCELLED;

    if (selector == 0 || extensions == 0 || extensions[0] == '\0' ||
        title == 0 || !bda_dialogs_internal_copy_string(
            selector->path, BDA_FILE_SELECTOR_PATH_SIZE, default_path
        )) {
        return BDA_FILE_SELECTOR_ERROR;
    }

    (void)bda_memset(
        selector->directory_state, 0, sizeof(selector->directory_state)
    );
    (void)bda_memset(&descriptor, 0, sizeof(descriptor));
    descriptor.path = selector->path;
    descriptor.extensions = extensions;
    descriptor.directory_state = selector->directory_state;
    descriptor.title = title;
    descriptor.selected_index = -1;
    descriptor.sentinel20 = -1;
    descriptor.sentinel24 = -1;
    descriptor.sentinel34 = -1;
    descriptor.sentinel38 = -1;
    descriptor.list_limit40 = 0x1000u;
    descriptor.sentinel48 = -1;

    if (!bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_DIALOGS_INTERNAL_GUI_FILE_SELECTOR_OPEN,
        1u
    )) {
        selector->path[0] = '\0';
        return BDA_FILE_SELECTOR_CANCELLED;
    }

    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_DIALOGS_INTERNAL_GUI_FILE_SELECTOR_RUN,
        (u32)&descriptor
    );

    if (descriptor.status != 0 && descriptor.status != -1 &&
        descriptor.list_head != 0 && descriptor.selected_index >= 0) {
        selected_node = (void *)bda_sdk_internal_call2(
            bda_sdk_internal_gui(),
            BDA_DIALOGS_INTERNAL_GUI_LIST_NTH,
            (u32)descriptor.list_head,
            (u32)descriptor.selected_index
        );
        if (selected_node != 0) {
            selected_path = *(const char **)selected_node;
            if (bda_dialogs_internal_join_path(
                selector->path, BDA_FILE_SELECTOR_PATH_SIZE, selected_path
            )) {
                result = BDA_FILE_SELECTOR_SELECTED;
            } else {
                result = BDA_FILE_SELECTOR_ERROR;
            }
        } else {
            result = BDA_FILE_SELECTOR_ERROR;
        }
    } else {
        selector->path[0] = '\0';
    }

    if (descriptor.list_head != 0) {
        (void)bda_sdk_internal_call1(
            bda_sdk_internal_gui(),
            BDA_DIALOGS_INTERNAL_GUI_LIST_FREE,
            (u32)descriptor.list_head
        );
    }
    return result;
}

#endif
