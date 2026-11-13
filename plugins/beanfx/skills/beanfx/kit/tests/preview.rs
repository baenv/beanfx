//! Port of tests/test_preview.py: tools/preview.html carries runtime/beanfx.js inline (a page opened from disk cannot
//! import a module). The copy between its RUNTIME START and RUNTIME END markers must be the runtime with `export `
//! removed. After changing the runtime, paste it into the page again between the markers.

use std::fs;
use std::path::PathBuf;

#[test]
fn preview_page_inlines_the_runtime() {
    let skill = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let page = fs::read_to_string(skill.join("tools/preview.html")).unwrap();
    let want = fs::read_to_string(skill.join("runtime/beanfx.js")).unwrap().replace("export ", "");
    let (start, end) = ("// RUNTIME START\n", "// RUNTIME END\n");
    let a = page.find(start).expect("RUNTIME START marker") + start.len();
    let b = page.find(end).expect("RUNTIME END marker");
    assert!(page[a..b] == want, "tools/preview.html: the inlined runtime differs from runtime/beanfx.js");
}
