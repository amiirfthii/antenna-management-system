export interface JalaliDate {
  year: number;
  month: number;
  day: number;
}

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

export const JALALI_MONTH_NAMES = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

export const JALALI_WEEKDAY_NAMES = ["ش", "ی", "د", "س", "چ", "پ", "ج"];

function div(a: number, b: number) {
  return Math.floor(a / b);
}

function mod(a: number, b: number) {
  return a - div(a, b) * b;
}

function jalCal(jy: number) {
  const breaks = [
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262,
    2324, 2394, 2456, 3178,
  ];
  const bl = breaks.length;
  let gy = jy + 621;
  let leapJ = -14;
  let jp = breaks[0];
  let jm = 0;
  let jump = 0;

  if (jy < breaks[0] || jy >= breaks[bl - 1]) {
    throw new Error(`Invalid Jalali year ${jy}`);
  }

  for (let i = 1; i < bl; i += 1) {
    jm = breaks[i];
    jump = jm - jp;
    if (jy < jm) break;
    leapJ += div(jump, 33) * 8 + div(mod(jump, 33), 4);
    jp = jm;
  }

  const n = jy - jp;
  leapJ += div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
  if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;

  const leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
  const march = 20 + leapJ - leapG;
  if (jump - n < 6) n = n - jump + div(jump + 4, 33) * 33;
  let leap = mod(mod(n + 1, 33) - 1, 4);
  if (leap === -1) leap = 4;

  return { leap, gy, march };
}

export function toJalaali(gy: number, gm: number, gd: number): JalaliDate {
  const g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  let jy = gy <= 1600 ? 0 : 979;
  gy -= gy <= 1600 ? 621 : 1600;
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    365 * gy +
    div(gy2 + 3, 4) -
    div(gy2 + 99, 100) +
    div(gy2 + 399, 400) -
    80 +
    gd +
    g_d_m[gm - 1];
  jy += 33 * div(days, 12053);
  days = mod(days, 12053);
  jy += 4 * div(days, 1461);
  days = mod(days, 1461);
  if (days > 365) {
    jy += div(days - 1, 365);
    days = mod(days - 1, 365);
  }
  const jm = days < 186 ? 1 + div(days, 31) : 7 + div(days - 186, 30);
  const jd = 1 + mod(days < 186 ? days : days - 186, days < 186 ? 31 : 30);
  return { year: jy, month: jm, day: jd };
}

export function toGregorian(jy: number, jm: number, jd: number) {
  const { gy, march } = jalCal(jy);
  let gd = march + (jm <= 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186) + jd - 1;
  let gm = 1;
  let gy2 = gy;
  const gDays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (div(gy2, 4) === gy2 / 4 && (div(gy2, 100) !== gy2 / 100 || div(gy2, 400) === gy2 / 400)) {
    gDays[2] = 29;
  }
  while (gd > gDays[gm]) {
    gd -= gDays[gm];
    gm += 1;
  }
  return { year: gy2, month: gm, day: gd };
}

export function jalaaliMonthLength(jy: number, jm: number) {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  const { leap } = jalCal(jy);
  return leap === 0 ? 30 : 29;
}

export function isValidJalaaliDate(jy: number, jm: number, jd: number) {
  return jm >= 1 && jm <= 12 && jd >= 1 && jd <= jalaaliMonthLength(jy, jm);
}

export function toLatinDigits(value: string) {
  return value.replace(/[۰-۹٠-٩]/g, (digit) => {
    const persianIndex = PERSIAN_DIGITS.indexOf(digit);
    if (persianIndex >= 0) return String(persianIndex);
    const arabicIndex = ARABIC_DIGITS.indexOf(digit);
    return arabicIndex >= 0 ? String(arabicIndex) : digit;
  });
}

export function pad2(value: number) {
  return value.toString().padStart(2, "0");
}

export function formatJalali(date: JalaliDate) {
  return `${date.year}/${pad2(date.month)}/${pad2(date.day)}`;
}

/** Normalize dot/slash Jalali date strings to YYYY/MM/DD (optional time preserved). */
export function normalizeJalaliDateString(value: string | null | undefined): string {
  if (value == null) return "";
  const s = toLatinDigits(String(value).trim());
  if (!s) return s;

  const match = s.match(/^(\d{4})[./](\d{1,2})[./](\d{1,2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?$/);
  if (match) {
    const [, year, month, day, timePart] = match;
    const normalized = `${year}/${pad2(Number(month))}/${pad2(Number(day))}`;
    return timePart ? `${normalized} ${timePart}` : normalized;
  }

  if (/^\d{4}\./.test(s)) {
    const spaceIdx = s.indexOf(" ");
    const datePart = spaceIdx < 0 ? s : s.slice(0, spaceIdx);
    const remainder = spaceIdx < 0 ? "" : s.slice(spaceIdx + 1);
    const parts = datePart.replace(/\./g, "/").split("/");
    let normalizedDate = datePart.replace(/\./g, "/");
    if (parts.length === 3) {
      normalizedDate = `${parts[0]}/${pad2(Number(parts[1]))}/${pad2(Number(parts[2]))}`;
    }
    return remainder ? `${normalizedDate} ${remainder}`.trim() : normalizedDate;
  }

  return s;
}

export function parseJalali(value: string): JalaliDate | null {
  const normalized = normalizeJalaliDateString(value);
  const dateOnly = normalized.split(/\s+/)[0] ?? "";
  const match = dateOnly.match(/^(\d{4})\/(\d{1,2})\/(\d{1,2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!isValidJalaaliDate(year, month, day)) return null;
  return { year, month, day };
}

export function getTodayJalali(): JalaliDate {
  const now = new Date();
  const { year, month, day } = toJalaali(now.getFullYear(), now.getMonth() + 1, now.getDate());
  return { year, month, day };
}

export function getTodayJalaliString() {
  return formatJalali(getTodayJalali());
}

export function getJalaliWeekday(jy: number, jm: number, jd: number) {
  const { year, month, day } = toGregorian(jy, jm, jd);
  return new Date(year, month - 1, day).getDay();
}

export function getJalaliMonthGrid(year: number, month: number) {
  const monthLength = jalaaliMonthLength(year, month);
  const firstWeekday = getJalaliWeekday(year, month, 1);
  const saturdayOffset = (firstWeekday + 1) % 7;
  const cells: Array<number | null> = [];

  for (let i = 0; i < saturdayOffset; i += 1) cells.push(null);
  for (let day = 1; day <= monthLength; day += 1) cells.push(day);
  while (cells.length % 7 !== 0) cells.push(null);

  return cells;
}
