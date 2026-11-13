//! Port of tests/test_kit.py: the helpers drafts used to write by hand: fl::Pen (put and line in world px),
//! pfx::contact, pfx::takes and the lt glow levels.

mod common;

use beanfx::fl::{self, Pen};
use beanfx::img;
use beanfx::lt;
use beanfx::ndarray::Array3;
use beanfx::pfx::{self, Contact, Takes};

fn solid(h: usize, w: usize, rgba: [u8; 4]) -> Array3<u8> {
    Array3::from_shape_fn((h, w, 4), |(_, _, c)| rgba[c])
}

fn lit(m: &beanfx::ndarray::Array2<i8>) -> Vec<(usize, usize)> {
    m.indexed_iter().filter(|(_, &v)| v >= 0).map(|(ix, _)| ix).collect()
}

#[test]
fn pen_put_lands_on_the_pixel_the_grid_reads() {
    let (w, h, px, py) = (40usize, 30usize, 17usize, 12usize);
    for dens in [1.0, 2.0] {
        let (x, y) = fl::wgrid(w, h, px as f64, py as f64, dens);
        let pen = Pen::new(px as f64, py as f64, dens);
        for (col, row) in [(px, py), (px - 7, py + 3), (px + 10, py - 9)] {
            let (wx, wy) = (x[[row, col]], y[[row, col]]);
            let mut m = fl::empty(w, h);
            pen.put(&mut m, wx, wy, 3);
            assert_eq!(lit(&m), vec![(row, col)], "Pen.put at density {dens} lands on ({wx}, {wy})");
        }
    }
}

#[test]
fn pen_line_runs_along_the_pivot_row() {
    let (px, py) = (17usize, 12usize);
    let mut m = fl::empty(40, 30);
    Pen::new(px as f64, py as f64, 1.0).line(&mut m, -5.5, 0.5, 4.5, 0.5, 2, false);
    let p = lit(&m);
    assert!(p.iter().all(|&(y, _)| y == py));
    assert_eq!(p.iter().map(|&(_, x)| x).min(), Some(px - 6));
    assert_eq!(p.iter().map(|&(_, x)| x).max(), Some(px + 4));
}

#[test]
fn contact_picks_labels_and_references() {
    let dir = common::tmpdir("kit_contact");
    let fr: Vec<_> = (0..25u32).map(|i| solid(10, 12, [(40 * i % 255) as u8, 80, 120, 255])).collect();
    let rf: Vec<_> = (0..51).map(|_| solid(16, 8, [200, 50, 50, 255])).collect();
    let p = dir.join("contact.png");
    let picks = pfx::contact(&p, &fr, 24.0, Contact { n: 6, scale: 2, ..Default::default() }).unwrap();
    assert_eq!(picks, vec![vec![Some(0), Some(5), Some(10), Some(14), Some(19), Some(24)]], "contact picks even phases");
    let one = img::read(&p).unwrap().dim();
    let picks = pfx::contact(&p, &fr, 24.0, Contact { n: 6, scale: 2, r#ref: Some((&rf, 30.0)), ..Default::default() }).unwrap();
    assert!(picks[0][0] == Some(0) && picks[0][5] == Some(24) && picks[1][0] == Some(0) && picks[1][5] == Some(50),
            "both rows end on the last frame");
    let two = img::read(&p).unwrap().dim();
    assert!(two.0 > one.0 && two.1 >= one.1, "the reference adds a row: {one:?} then {two:?}");
    let picks = pfx::contact(&p, &fr, 24.0, Contact { n: 6, r#ref: Some((&rf, 30.0)), by: "time".into(), ..Default::default() }).unwrap();
    assert!(picks[0][5].is_none() && picks[0][3].is_some() && picks[1][5] == Some(50), "by time a shorter run leaves its late cells empty: {picks:?}");
    let half = vec![Array3::<u8>::zeros((10, 12, 4)); 3];
    pfx::contact(&p, &half, 12.0, Contact { n: 3, ..Default::default() }).unwrap();
    let a = img::read_rgb(&p).unwrap();
    assert_eq!([a[[20, 20, 0]], a[[20, 20, 1]], a[[20, 20, 2]]], [16, 16, 24], "transparency goes over bg");
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn takes_sit_side_by_side_and_write_a_gif_in_step() {
    let dir = common::tmpdir("kit_takes");
    let dim: Vec<_> = (0..4).map(|_| solid(10, 12, [60, 30, 20, 255])).collect();
    let bright: Vec<_> = (0..6u8).map(|i| solid(10, 12, [250, 200, 100 + 20 * i, 255])).collect();
    let p = dir.join("glow_takes.png");
    let out = pfx::takes(&p, &[("subtle", dim.clone()), ("strong", bright)], Takes { fps: Some(12.0), scale: 3, ..Default::default() }).unwrap();
    let names: Vec<String> = out.iter().map(|q| q.file_name().unwrap().to_string_lossy().into()).collect();
    assert_eq!(names, ["glow_takes.png", "glow_takes.gif"], "takes writes the png and the gif");
    let im = img::read_rgb(&p).unwrap();
    assert_eq!(im.dim().1, 2 * (12 * 3 + 8) + 8, "two takes side by side: width");
    let mid = 8 + 16 + 15;
    let px = |y: usize, x: usize| [im[[y, x, 0]], im[[y, x, 1]], im[[y, x, 2]]];
    assert!(px(mid, 8 + 18) == [60, 30, 20] && px(mid, 8 + 44 + 18) == [250, 200, 100], "each take sits in its own column");
    let mut opts = gif::DecodeOptions::new();
    opts.set_color_output(gif::ColorOutput::RGBA);
    let mut d = opts.read_info(std::fs::File::open(&out[1]).unwrap()).unwrap();
    let mut n = 0;
    while d.read_next_frame().unwrap().is_some() {
        n += 1;
    }
    assert_eq!(n, 6, "the gif runs as long as the longest take");
    let out = pfx::takes(dir.join("shape_takes.png"), &[("coiled", dim[..1].to_vec()), ("dive", vec![solid(10, 12, [250, 200, 100, 255])])],
                         Takes { fps: Some(12.0), ..Default::default() }).unwrap();
    assert_eq!(out.len(), 1, "peak frames alone write no gif");
    std::fs::remove_dir_all(&dir).ok();
}

#[test]
fn glow_levels_in_order_of_strength() {
    let lv: Vec<_> = ["subtle", "medium", "strong"].iter().map(|k| lt::glow_level(k).unwrap()).collect();
    assert!(lv.windows(2).all(|w| w[0].pool_k < w[1].pool_k && w[0].mean.1 <= w[1].mean.1), "glow levels grow from subtle to strong");
}
