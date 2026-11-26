package de.wallura.app;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Kleine Fabriken für die Bausteine der Handy-Oberfläche. */
final class Ui {

    static final int PRIMARY = 0;
    static final int SECONDARY = 1;
    static final int DANGER = 2;
    static final int GHOST = 3;
    static final int CHIP_ON = 4;
    static final int CHIP_OFF = 5;

    private Ui() {
    }

    static int dp(Context c, float value) {
        return Math.round(c.getResources().getDisplayMetrics().density * value);
    }

    static int col(Context c, int resId) {
        return c.getColor(resId);
    }

    static TextView text(Context c, String value, int sizeSp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(value);
        t.setTextSize(sizeSp);
        t.setTextColor(color);
        if (bold) {
            t.setTypeface(Typeface.DEFAULT_BOLD);
        }
        return t;
    }

    /** Knopf im Stil der App (primär, secondary, danger, ghost, chips). */
    static TextView pill(Context c, String label, int kind) {
        int colorRes;
        int background;
        switch (kind) {
            case PRIMARY:
                colorRes = R.color.on_accent;
                background = R.drawable.bg_btn_primary;
                break;
            case DANGER:
                colorRes = R.color.danger_text;
                background = R.drawable.bg_btn_danger;
                break;
            case GHOST:
                colorRes = R.color.muted;
                background = R.drawable.bg_btn_ghost;
                break;
            case CHIP_ON:
                colorRes = R.color.text;
                background = R.drawable.bg_chip_on;
                break;
            case CHIP_OFF:
                colorRes = R.color.muted;
                background = R.drawable.bg_chip_off;
                break;
            default:
                colorRes = R.color.text;
                background = R.drawable.bg_btn_secondary;
                break;
        }
        boolean chip = kind == CHIP_ON || kind == CHIP_OFF;
        TextView t = text(c, label, chip ? 12 : 13, col(c, colorRes), kind == PRIMARY);
        t.setGravity(Gravity.CENTER);
        t.setBackgroundResource(background);
        t.setPadding(dp(c, chip ? 14 : 16), dp(c, chip ? 9 : 10),
                dp(c, chip ? 14 : 16), dp(c, chip ? 9 : 10));
        t.setMinHeight(dp(c, chip ? 36 : 44));
        t.setMinWidth(0);
        t.setClickable(true);
        t.setFocusable(true);
        return t;
    }

    /** Abschnitt: Überschrift und Karte, die die Zeilen aufnimmt. */
    static LinearLayout section(Context c, LinearLayout parent, String title) {
        TextView headline = text(c, title, 14, col(c, R.color.text), true);
        LinearLayout.LayoutParams headlineParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        headlineParams.topMargin = dp(c, 18);
        headlineParams.bottomMargin = dp(c, 8);
        parent.addView(headline, headlineParams);

        LinearLayout card = new LinearLayout(c);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        int pad = dp(c, 14);
        card.setPadding(pad, pad, pad, dp(c, 4));
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        cardParams.bottomMargin = dp(c, 10);
        parent.addView(card, cardParams);
        return card;
    }

    /**
     * Zeile in einer Karte: Titel und Beschreibung übereinander, die Steuerelemente
     * kommen darunter in {@link #controls}. So bleibt auf dem Handy alles lesbar.
     */
    static LinearLayout block(Context c, LinearLayout card, String title, String desc) {
        LinearLayout box = new LinearLayout(c);
        box.setOrientation(LinearLayout.VERTICAL);

        box.addView(text(c, title, 14, col(c, R.color.text), false));

        TextView descView = null;
        if (desc != null && !desc.isEmpty()) {
            descView = text(c, desc, 11, col(c, R.color.muted), false);
            descView.setLineSpacing(dp(c, 1), 1.15f);
            LinearLayout.LayoutParams descParams = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
            descParams.topMargin = dp(c, 3);
            box.addView(descView, descParams);
        }
        box.setTag(descView);

        LinearLayout.LayoutParams boxParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        boxParams.topMargin = dp(c, 8);
        boxParams.bottomMargin = dp(c, 8);
        card.addView(box, boxParams);
        return box;
    }

    /** Eigene Zeile unter Titel/Beschreibung, in die die Steuerelemente kommen. */
    static LinearLayout controls(Context c, LinearLayout block) {
        LinearLayout row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(c, 10);
        block.addView(row, params);
        return row;
    }

    /**
     * Chip-Reihe, die auf schmalen Handys seitlich scrollt, statt gequetscht zu werden.
     * Die Reihe hängt danach schon in der Karte.
     */
    static LinearLayout chipScroll(Context c, LinearLayout card) {
        LinearLayout row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        HorizontalScrollView scroll = new HorizontalScrollView(c);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(row, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.bottomMargin = dp(c, 6);
        card.addView(scroll, params);
        return row;
    }

    /** Volle Breite für ein einzelnes Steuerelement in {@link #controls}. */
    static void wide(LinearLayout row, View view) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        row.addView(view, params);
    }
}
