/* OoT by default; one unsupported instrument makes the ENTIRE song piano.
   Usage: render_synth oot.sf2|- piano.sf2 input.mid seconds mapping.tsv > out.s16
   Preflight examines all converted MIDI events, including beyond the preview.
   Output: 44100 Hz stereo signed 16-bit native-endian PCM. Original code: MIT. */
#include <stdio.h>
#include <stdlib.h>
#define TSF_IMPLEMENTATION
#include "tools/tsf.h"
#define TML_IMPLEMENTATION
#include "tools/tml.h"

static int named_preset(tsf *s, const char *name) {
    for (int i = 0; i < tsf_get_presetcount(s); i++)
        if (!strcmp(tsf_get_presetname(s, i), name)) return i;
    return -1;
}

int main(int argc, char **argv) {
    if (argc != 6) return 2;
    char *tail;
    double seconds = strtod(argv[4], &tail);
    if (tail == argv[4] || *tail || !(seconds > 0 && seconds <= 3600)) return 2;
    tml_message *head = tml_load_filename(argv[3]);
    if (!head) { fprintf(stderr, "Could not load MIDI\n"); return 1; }
    tsf *s = strcmp(argv[1], "-") ? tsf_load_filename(argv[1]) : NULL;
    int presets[128], channels[16], unknown = 0, banks = 0, unassigned = 0;
    for (int i = 0; i < 128; i++) presets[i] = -1;
    for (int i = 0; i < 16; i++) channels[i] = -1;
    const char *reason = s ? "" : "OoT SoundFont unavailable";
    if (s) {
        FILE *mapping = fopen(argv[5], "r");
        if (!mapping) { fprintf(stderr, "Could not load mapping\n"); tsf_close(s); tml_free(head); return 1; }
        char line[256], name[128];
        int program;
        while (fgets(line, sizeof(line), mapping)) {
            if (sscanf(line, "%d\t%127[^\n]", &program, name) != 2 || program < 0 || program > 127) {
                fprintf(stderr, "Invalid program mapping\n"); fclose(mapping); tsf_close(s); tml_free(head); return 1;
            }
            presets[program] = named_preset(s, name);
        }
        fclose(mapping);
        /* Scan the entire song before emitting a single sample. Never mix modes. */
        for (tml_message *m = head; m; m = m->next) {
            int ch = m->channel;
            if (ch > 15) continue;
            if (m->type == TML_PROGRAM_CHANGE) {
                int raw = (unsigned char)m->program;
                channels[ch] = raw < 128 ? presets[raw] : -1;
                if (channels[ch] < 0) {
                    unknown++;
                    fprintf(stderr, "Unmapped program %d on channel %d at %u ms\n", raw, ch + 1, m->time);
                }
            } else if (m->type == TML_CONTROL_CHANGE && (m->control == 0 || m->control == 32)) {
                banks++;
                fprintf(stderr, "Unsupported bank change CC%d=%d on channel %d at %u ms\n",
                        m->control, m->control_value, ch + 1, m->time);
            } else if (m->type == TML_NOTE_ON && m->velocity && channels[ch] < 0) {
                unassigned++;
            }
        }
        if (unknown) reason = "Unmapped instrument in full song";
        else if (banks) reason = "Unsupported bank change in full song";
        else if (unassigned) reason = "Note without a mapped instrument in full song";
    }
    int oot = s && !*reason;
    int piano = -1;
    if (!oot) {
        if (s) tsf_close(s);
        s = tsf_load_filename(argv[2]);
        if (s) {
            piano = named_preset(s, "Piano");
            if (piano < 0) piano = tsf_get_presetindex(s, 0, 0);
        }
        if (!s || piano < 0) {
            fprintf(stderr, "Could not load fallback piano preset\n");
            if (s) tsf_close(s);
            tml_free(head); return 1;
        }
    }
    tsf_set_output(s, TSF_STEREO_INTERLEAVED, 44100, -12.0f);
    for (int ch = 0; ch < 16; ch++) {
        if (!oot) tsf_channel_set_presetindex(s, ch, piano);
        tsf_channel_set_pitchrange(s, ch, 12.0f);
    }
    short pcm[1024];
    unsigned long frame = 0, end = (unsigned long)(44100 * seconds), notes = 0;
    tml_message *m = head;
    while (frame < end) {
        while (m && (unsigned long long)m->time * 44100 / 1000 <= frame) {
            int ch = m->channel;
            if (ch <= 15) switch (m->type) {
                case TML_PROGRAM_CHANGE:
                    if (oot) tsf_channel_set_presetindex(s, ch, presets[m->program]);
                    break;
                case TML_NOTE_ON:
                    if (m->velocity) { tsf_channel_note_on(s, ch, m->key, m->velocity / 127.0f); notes++; }
                    else tsf_channel_note_off(s, ch, m->key);
                    break;
                case TML_NOTE_OFF: tsf_channel_note_off(s, ch, m->key); break;
                case TML_PITCH_BEND: tsf_channel_set_pitchwheel(s, ch, m->pitch_bend); break;
                case TML_CONTROL_CHANGE:
                    if (m->control == 7 || m->control == 10 || m->control == 11 || m->control == 64)
                        tsf_channel_midi_control(s, ch, m->control, m->control_value);
                    break;
            }
            m = m->next;
        }
        unsigned long count = end - frame;
        if (count > 512) count = 512;
        if (m) {
            unsigned long long next = (unsigned long long)m->time * 44100 / 1000;
            if (next - frame < count) count = (unsigned long)(next - frame);
        }
        tsf_render_short(s, pcm, (int)count, 0);
        if (fwrite(pcm, sizeof(short) * 2, count, stdout) != count) { tsf_close(s); tml_free(head); return 1; }
        frame += count;
    }
    fprintf(stderr, "STATS {\"mode\":\"%s\",\"fallback_reason\":\"%s\",\"frames\":%lu,"
            "\"mapped_note_ons\":%lu,\"fallback_note_ons\":%lu,\"unknown_program_events\":%d,"
            "\"unsupported_bank_events\":%d,\"unassigned_note_ons\":%d}\n",
            oot ? "oot" : "piano", reason, frame, oot ? notes : 0, oot ? 0 : notes, unknown, banks, unassigned);
    tml_free(head); tsf_close(s);
    return 0;
}
