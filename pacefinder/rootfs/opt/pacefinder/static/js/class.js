// Shared car-class resolver (docs/specs/class-from-pi.md).
//
// We never trusted PI before — we decoded Forza's UDP car_class integer
// through a map that conflated Horizon (S1/S2) and Motorsport (R/P),
// missing E and single-S. Derive from car_pi using the Forza Motorsport
// 2023 (Motorsport Series) ranges instead. PI is the authoritative
// number; the integer is the thing we know is mislabelled — so prefer
// PI, fall back to the legacy integer map only when PI is absent
// (never a worse badge than before).
//
// FH4/5 (Horizon) ranges differ; the FM-vs-FH packet variant isn't
// persisted yet, so this assumes FM2023 — the only active game. Revisit
// if FH5 is unparked (see the spec's open questions).
function pfCarClass(pi, clsInt){
  pi = (pi == null || pi === '') ? null : +pi;
  if(pi && pi > 0){
    if(pi <= 300) return 'E';
    if(pi <= 400) return 'D';
    if(pi <= 500) return 'C';
    if(pi <= 600) return 'B';
    if(pi <= 700) return 'A';
    if(pi <= 800) return 'S';
    if(pi <= 900) return 'R';
    if(pi <= 998) return 'P';
    return 'X';
  }
  // Legacy fallback — Forza's car_class enum index (no PI available).
  const M = {0:'D',1:'C',2:'B',3:'A',4:'S1',5:'S2',6:'X',7:'R',8:'P'};
  return (clsInt != null && M[clsInt]) ? M[clsInt] : '';
}
