/* CXM V0.5: stable T0–T11 identity colours; never use colour alone for status. */
(function () {
  'use strict';
  const PALETTE = Object.freeze([
    '#B6C4D5', // T0 reference
    '#53D68A', // T1
    '#5BAAFF', // T2
    '#C49AFF', // T3
    '#F7C66A', // T4
    '#F38FB9', // T5
    '#54DCCB', // T6
    '#FFAD73', // T7
    '#91A0FF', // T8
    '#FF8588', // T9
    '#B2DA75', // T10
    '#D4A7D9'  // T11
  ]);
  const color = n => Number.isInteger(n) && n >= 0 && n < PALETTE.length ? PALETTE[n] : '#B6C4D5';
  const api = Object.freeze({color, palette: PALETTE});
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  if (typeof window !== 'undefined') window.CXMToolStyle=api;
})();
