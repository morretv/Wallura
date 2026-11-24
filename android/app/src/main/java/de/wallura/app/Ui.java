package de.wallura.app;

import android.content.Context;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Kleine Fabriken für die im PC-Design gehaltenen Bausteine. */
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

    /** Button im Stil der PC-Buttons (primaer, secondary, danger, ghost, chips). */
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
        TextView t = text(c, label, chip ? 10 : 11, col(c, colorRes), kind == PRIMARY);
        t.setGravity(Gravity.CENTER);
        t.setBackgroundResource(background);
        int padH = dp(c, 10);
        int padV = dp(c, 8);
        t.setPadding(padH, padV, padH, padV);
        t.setClickable(true);
        t.setFocusable(true);
        return t;
    }

    /** Sektion wie am PC: Titel + Karte. Die Karte nimmt die Zeilen auf. */
    static LinearLayout section(Context c, LinearLayout parent, String title) {
        TextView headline = text(c, title, 13, col(c, R.color.text), true);
        LinearLayout.LayoutParams headlineParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        headlineParams.topMargin = dp(c, 10);
        headlineParams.bottomMargin = dp(c, 6);
        parent.addView(headline, headlineParams);

        LinearLayout card = new LinearLayout(c);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        int pad = dp(c, 10);
        card.setPadding(pad + dp(c, 2), pad, pad + dp(c, 2), pad);
        LinearLayout.LayoutParams cardParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        cardParams.bottomMargin = dp(c, 10);
        parent.addView(card, cardParams);
        return card;
    }

    /** Zeile wie am PC: Titel + Beschreibung links, Platz für ein Steuerelement rechts. */
    static LinearLayout block(Context c, LinearLayout card, String title, String desc) {
        LinearLayout row = new LinearLayout(c);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);

        LinearLayout texts = new LinearLayout(c);
        texts.setOrientation(LinearLayout.VERTICAL);
        texts.setLayoutParams(new LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        texts.addView(text(c, title, 11, col(c, R.color.text), false));

        TextView descView = null;
        if (desc != null && !desc.isEmpty()) {
            descView = text(c, desc, 9, col(c, R.color.muted), false);
            descView.setLineSpacing(0f, 1.1f);
            texts.addView(descView);
        }
        row.addView(texts);
        row.setTag(descView);

        LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        rowParams.topMargin = dp(c, 6);
        rowParams.bottomMargin = dp(c, 6);
        card.addView(row, rowParams);
        return row;
    }
}
