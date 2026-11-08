/** Payment timestamps are stored as UTC (some legacy API responses omit Z).
 * Display in Tehran independently of the browser's and server's timezone.
 * Never rewrite timestamps persisted in PostgreSQL.
 */
export function paymentDateTehran(value:unknown):string{
  if(value===null||value===undefined||value==="")return "—";
  const raw=String(value).trim();
  // SQLAlchemy UTC-naive ISO timestamps: YYYY-MM-DDTHH:mm:ss[.ffffff].
  // Explicit offsets and Z are preserved; date-only strings are not reinterpreted.
  const normalized=/^\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?$/.test(raw)
    ?raw.replace(" ","T")+"Z"
    :raw;
  const date=new Date(normalized);
  return Number.isNaN(date.getTime())?raw:date.toLocaleString("fa-IR",{timeZone:"Asia/Tehran"});
}
