// usage: osascript -l JavaScript pdftext.js <in.pdf> <out.txt>   (extracts text only)
ObjC.import('PDFKit'); ObjC.import('Foundation');
function run(argv) {
  const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  if (!doc || doc.isNil()) return "cannot open";
  let s = "";
  for (let i = 0; i < doc.pageCount; i++) { const p = doc.pageAtIndex(i); s += (p.string.js || "") + "\n\f\n"; }
  $.NSString.alloc.initWithUTF8String(s).writeToFileAtomicallyEncodingError(argv[1], true, $.NSUTF8StringEncoding, null);
  return doc.pageCount + " pages";
}
