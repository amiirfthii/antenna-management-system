import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import {
  formatJalali,
  getJalaliMonthGrid,
  getTodayJalali,
  JALALI_MONTH_NAMES,
  JALALI_WEEKDAY_NAMES,
  normalizeJalaliDateString,
  parseJalali,
  type JalaliDate,
} from "../utils/jalaliDate";

interface JalaliDatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  inputStyle?: React.CSSProperties;
}

export default function JalaliDatePicker({
  value,
  onChange,
  placeholder = "1404/09/05",
  inputStyle,
}: JalaliDatePickerProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [popupStyle, setPopupStyle] = useState<React.CSSProperties>({});
  const today = useMemo(() => getTodayJalali(), []);
  const parsed = useMemo(() => parseJalali(value), [value]);
  const [viewYear, setViewYear] = useState(parsed?.year ?? today.year);
  const [viewMonth, setViewMonth] = useState(parsed?.month ?? today.month);

  useEffect(() => {
    if (parsed) {
      setViewYear(parsed.year);
      setViewMonth(parsed.month);
    }
  }, [parsed?.year, parsed?.month]);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        !rootRef.current?.contains(target) &&
        !popupRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    if (!open || !rootRef.current) return;

    const updatePosition = () => {
      if (!rootRef.current) return;
      const rect = rootRef.current.getBoundingClientRect();
      setPopupStyle({
        position: "fixed",
        top: rect.bottom + 8,
        left: rect.left,
        width: Math.max(rect.width, 300),
        zIndex: 10050,
        minWidth: 300,
        background: "linear-gradient(160deg, #0f172afa, #020617fc)",
        borderRadius: 18,
        border: "1px solid rgba(251, 146, 60, 0.35)",
        boxShadow: "0 28px 60px rgba(0, 0, 0, 0.65)",
        padding: "1rem",
      });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  const monthGrid = useMemo(
    () => getJalaliMonthGrid(viewYear, viewMonth),
    [viewYear, viewMonth],
  );

  const selectDate = (date: JalaliDate) => {
    onChange(formatJalali(date));
    setOpen(false);
  };

  const goMonth = (delta: number) => {
    let nextMonth = viewMonth + delta;
    let nextYear = viewYear;
    if (nextMonth > 12) {
      nextMonth = 1;
      nextYear += 1;
    } else if (nextMonth < 1) {
      nextMonth = 12;
      nextYear -= 1;
    }
    setViewMonth(nextMonth);
    setViewYear(nextYear);
  };

  const defaultInputStyle: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "0.72rem 2.6rem 0.72rem 4.8rem",
    borderRadius: 14,
    border: "1px solid rgba(148, 163, 184, 0.35)",
    outline: "none",
    direction: "ltr",
    textAlign: "left",
    background: "rgba(15, 23, 42, 0.92)",
    color: "#f8fafc",
    fontSize: "0.92rem",
    ...inputStyle,
  };

  return (
    <div
      ref={rootRef}
      className="jalali-date-picker-root"
      style={{ position: "relative", zIndex: open ? 500 : "auto" }}
    >
      <div style={{ position: "relative" }}>
        <CalendarDays
          size={18}
          style={{
            position: "absolute",
            right: 14,
            top: "50%",
            transform: "translateY(-50%)",
            color: "#94a3b8",
            pointerEvents: "none",
            zIndex: 1,
          }}
        />
        <input
          type="text"
          value={value}
          placeholder={placeholder}
          readOnly
          onClick={() => setOpen(true)}
          onFocus={() => setOpen(true)}
          style={{ ...defaultInputStyle, cursor: "pointer" }}
          title="انتخاب از تقویم"
        />
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          style={{
            position: "absolute",
            left: 8,
            top: "50%",
            transform: "translateY(-50%)",
            border: "none",
            borderRadius: 10,
            padding: "0.35rem 0.5rem",
            background: "rgba(251, 146, 60, 0.15)",
            color: "#fdba74",
            cursor: "pointer",
            fontSize: "0.72rem",
            fontWeight: 700,
            zIndex: 2,
          }}
        >
          تقویم
        </button>
      </div>

      {open &&
        createPortal(
          <div ref={popupRef} className="jalali-picker-popup" style={popupStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 10,
              }}
            >
              <button
                type="button"
                onClick={() => goMonth(-1)}
                style={navButtonStyle}
                aria-label="ماه قبل"
              >
                <ChevronRight size={16} />
              </button>
              <div style={{ fontWeight: 700, color: "#f8fafc", fontSize: "0.95rem" }}>
                {JALALI_MONTH_NAMES[viewMonth - 1]} {viewYear}
              </div>
              <button
                type="button"
                onClick={() => goMonth(1)}
                style={navButtonStyle}
                aria-label="ماه بعد"
              >
                <ChevronLeft size={16} />
              </button>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(7, 1fr)",
                gap: 4,
                marginBottom: 4,
              }}
            >
              {JALALI_WEEKDAY_NAMES.map((name) => (
                <div
                  key={name}
                  style={{
                    textAlign: "center",
                    fontSize: "0.72rem",
                    color: "#64748b",
                    fontWeight: 700,
                  }}
                >
                  {name}
                </div>
              ))}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(7, 1fr)",
                gap: 4,
              }}
            >
              {monthGrid.map((day, index) => {
                if (!day) {
                  return <div key={`empty-${index}`} style={{ height: 34 }} />;
                }

                const isSelected =
                  parsed?.year === viewYear &&
                  parsed?.month === viewMonth &&
                  parsed?.day === day;
                const isToday =
                  today.year === viewYear && today.month === viewMonth && today.day === day;

                return (
                  <button
                    key={`${viewYear}-${viewMonth}-${day}`}
                    type="button"
                    onClick={() => selectDate({ year: viewYear, month: viewMonth, day })}
                    style={{
                      height: 34,
                      borderRadius: 10,
                      border: isToday ? "1px solid #f97316" : "1px solid transparent",
                      background: isSelected
                        ? "linear-gradient(135deg,#ff8a3d,#ffb347)"
                        : isToday
                          ? "rgba(249,115,22,0.12)"
                          : "transparent",
                      color: isSelected ? "#111827" : "#e2e8f0",
                      cursor: "pointer",
                      fontWeight: isSelected || isToday ? 700 : 500,
                      fontSize: "0.82rem",
                    }}
                  >
                    {day}
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={() => selectDate(today)}
              style={{
                width: "100%",
                marginTop: 10,
                border: "1px solid rgba(251, 146, 60, 0.35)",
                borderRadius: 12,
                padding: "0.45rem",
                background: "rgba(251, 146, 60, 0.12)",
                color: "#fdba74",
                cursor: "pointer",
                fontWeight: 700,
                fontSize: "0.78rem",
              }}
            >
              امروز
            </button>
          </div>,
          document.body,
        )}
    </div>
  );
}

const navButtonStyle: React.CSSProperties = {
  border: "1px solid rgba(251, 146, 60, 0.25)",
  borderRadius: 10,
  width: 32,
  height: 32,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(15, 23, 42, 0.85)",
  cursor: "pointer",
  color: "#fdba74",
};
