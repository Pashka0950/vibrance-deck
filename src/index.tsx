import { callable, definePlugin } from "@decky/api";
import {
  DialogButton,
  Focusable,
  PanelSection,
  PanelSectionRow,
  SliderField,
  ToggleField,
} from "@decky/ui";
import { useEffect, useRef, useState } from "react";

type Lang = "auto" | "ru" | "en";
type State = { level: number; enabled: boolean; lang: Lang };

const getState = callable<[], State>("get_state");
const setState = callable<[level: number, enabled: boolean], boolean>("set_state");
const setLang = callable<[lang: Lang], boolean>("set_lang");

// Russian UI when Steam (or the system) language is Russian
function isRussian(): boolean {
  try {
    const loc = (window as any).LocalizationManager?.m_rgLocalesToUse?.[0];
    if (typeof loc === "string") return loc.toLowerCase().startsWith("russian") || loc.startsWith("ru");
  } catch (e) {}
  return (navigator.language || "").toLowerCase().startsWith("ru");
}
const SYSTEM_RU = isRussian();

const PRESETS = [50, 60, 70, 80, 100];

const chip = (active: boolean): any => ({
  minWidth: 0,
  padding: "6px 0",
  flex: 1,
  fontSize: "12px",
  background: active ? "#1a9fff" : undefined,
  color: active ? "#fff" : undefined,
});

function DropIcon() {
  return (
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2.5c-.3 0-.6.2-.8.4C9.4 5.3 5 11 5 15a7 7 0 0 0 14 0c0-4-4.4-9.7-6.2-12.1-.2-.2-.5-.4-.8-.4z" />
    </svg>
  );
}

function Content() {
  const [state, setLocal] = useState<State | null>(null);
  const [error, setError] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    getState().then(setLocal).catch(() => setError(true));
  }, []);

  // Slider fires many events while dragging - send the last one after a short pause
  const push = (next: State, immediate = false) => {
    setLocal(next);
    window.clearTimeout(timer.current);
    const send = () =>
      setState(next.level, next.enabled)
        .then((ok) => setError(!ok))
        .catch(() => setError(true));
    if (immediate) send();
    else timer.current = window.setTimeout(send, 150);
  };

  const ru = state ? state.lang === "ru" || (state.lang === "auto" && SYSTEM_RU) : SYSTEM_RU;
  const t = (r: string, e: string) => (ru ? r : e);

  if (!state) {
    return (
      <PanelSection>
        <PanelSectionRow>{error ? t("Ошибка загрузки", "Failed to load") : t("Загрузка…", "Loading…")}</PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
    <PanelSection title={t("Насыщенность экрана", "Screen saturation")}>
      <PanelSectionRow>
        <ToggleField
          label={t("Включено", "Enabled")}
          checked={state.enabled}
          onChange={(v: boolean) => push({ ...state, enabled: v }, true)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          label={t("Цифровая яркость", "Digital vibrance")}
          description={
            state.level === 50
              ? t("50% - как было", "50% - unchanged")
              : t("50% - обычно, 0% - ч/б, 100% - максимум", "50% normal, 0% greyscale, 100% max")
          }
          value={state.level}
          min={0}
          max={100}
          step={1}
          showValue
          valueSuffix="%"
          notchCount={11}
          disabled={!state.enabled}
          onChange={(v: number) => push({ ...state, level: v })}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <Focusable style={{ display: "flex", gap: "4px" }}>
          {PRESETS.map((p) => (
            <DialogButton
              key={p}
              style={chip(state.enabled && state.level === p)}
              onClick={() => push({ ...state, level: p, enabled: true }, true)}
            >
              {p}%
            </DialogButton>
          ))}
        </Focusable>
      </PanelSectionRow>
      {error && (
        <PanelSectionRow>
          <div style={{ color: "#ff6b6b", fontSize: "12px" }}>
            {t("Не удалось применить. Попробуй ещё раз.", "Could not apply. Please try again.")}
          </div>
        </PanelSectionRow>
      )}
    </PanelSection>
    <PanelSection title={t("Язык", "Language")}>
      <PanelSectionRow>
        <Focusable style={{ display: "flex", gap: "4px" }}>
          {([
            ["auto", t("Авто", "Auto")],
            ["ru", "RU"],
            ["en", "EN"],
          ] as [Lang, string][]).map(([code, label]) => (
            <DialogButton
              key={code}
              style={chip(state.lang === code)}
              onClick={() => {
                setLocal({ ...state, lang: code });
                setLang(code).catch(() => setError(true));
              }}
            >
              {label}
            </DialogButton>
          ))}
        </Focusable>
      </PanelSectionRow>
    </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "Vibrance",
  content: <Content />,
  icon: <DropIcon />,
}));
