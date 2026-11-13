//! PNG in and out and the two PIL calls the kit makes: Image.convert("RGBA" / "RGB") and resize(..., Image.BOX),
//! bit for bit with Pillow. Images are (h, w, c) u8 arrays: c 4 RGBA, 3 RGB, 2 LA, 1 L.

use ndarray::{s, Array3, ArrayView3};
use std::fs::File;
use std::io::BufWriter;
use std::path::Path;

/// Reads a PNG as it decodes: palette and tRNS expanded (as PIL's convert applies them), 16-bit cut to its high byte.
pub fn read_raw(path: impl AsRef<Path>) -> Result<Array3<u8>, String> {
    let path = path.as_ref();
    let f = File::open(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut dec = png::Decoder::new(f);
    dec.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut rd = dec.read_info().map_err(|e| format!("{}: {e}", path.display()))?;
    let mut buf = vec![0; rd.output_buffer_size()];
    let info = rd.next_frame(&mut buf).map_err(|e| format!("{}: {e}", path.display()))?;
    let c = rd.output_color_type().0.samples();
    buf.truncate(info.buffer_size());
    Array3::from_shape_vec((info.height as usize, info.width as usize, c), buf).map_err(|e| e.to_string())
}

/// Image.open(path).convert("RGBA").
pub fn read(path: impl AsRef<Path>) -> Result<Array3<u8>, String> {
    convert_rgba(&read_raw(path)?.view())
}

/// Image.open(path).convert("RGB").
pub fn read_rgb(path: impl AsRef<Path>) -> Result<Array3<u8>, String> {
    convert_rgb(&read_raw(path)?.view())
}

/// PIL convert("RGBA"): grey spreads to r, g, b; alpha 255 where there is none.
pub fn convert_rgba(a: &ArrayView3<u8>) -> Result<Array3<u8>, String> {
    let (h, w, c) = a.dim();
    let mut out = Array3::zeros((h, w, 4));
    for y in 0..h {
        for x in 0..w {
            let p = |k: usize| a[[y, x, k]];
            let v = match c {
                1 => [p(0), p(0), p(0), 255],
                2 => [p(0), p(0), p(0), p(1)],
                3 => [p(0), p(1), p(2), 255],
                4 => [p(0), p(1), p(2), p(3)],
                _ => return Err(format!("convert: {c} channels")),
            };
            for k in 0..4 {
                out[[y, x, k]] = v[k];
            }
        }
    }
    Ok(out)
}

/// PIL convert("RGB"): alpha dropped, not composited.
pub fn convert_rgb(a: &ArrayView3<u8>) -> Result<Array3<u8>, String> {
    let c = a.dim().2;
    if c >= 3 {
        return Ok(a.slice(s![.., .., 0..3]).to_owned());
    }
    Ok(convert_rgba(a)?.slice(s![.., .., 0..3]).to_owned())
}

/// Writes (h, w, c) as a PNG: c 4 RGBA, 3 RGB, 2 grey and alpha, 1 grey.
pub fn write(path: impl AsRef<Path>, a: &ArrayView3<u8>) -> Result<(), String> {
    let path = path.as_ref();
    let (h, w, c) = a.dim();
    let ct = match c {
        4 => png::ColorType::Rgba,
        3 => png::ColorType::Rgb,
        2 => png::ColorType::GrayscaleAlpha,
        1 => png::ColorType::Grayscale,
        _ => return Err(format!("write: {c} channels")),
    };
    let f = File::create(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut enc = png::Encoder::new(BufWriter::new(f), w as u32, h as u32);
    enc.set_color(ct);
    enc.set_depth(png::BitDepth::Eight);
    let mut wr = enc.write_header().map_err(|e| e.to_string())?;
    let data: Vec<u8> = a.iter().copied().collect();
    wr.write_image_data(&data).map_err(|e| e.to_string())
}

const PRECISION_BITS: u32 = 32 - 8 - 2;

/// Pillow's precompute_coeffs for the box filter, made 8-bit fixed point: per output pixel (first input, weights).
fn coeffs(in_size: usize, out_size: usize) -> Vec<(usize, Vec<i32>)> {
    let scale = in_size as f64 / out_size as f64;
    let filterscale = scale.max(1.0);
    let support = 0.5 * filterscale;
    let ss = 1.0 / filterscale;
    (0..out_size)
        .map(|xx| {
            let center = (xx as f64 + 0.5) * scale;
            let xmin = ((center - support + 0.5) as i64).max(0) as usize;
            let xmax = ((center + support + 0.5) as i64).min(in_size as i64) as usize - xmin;
            let mut k: Vec<f64> = (0..xmax)
                .map(|x| {
                    let t = (x as f64 + xmin as f64 - center + 0.5) * ss;
                    if t > -0.5 && t <= 0.5 { 1.0 } else { 0.0 }
                })
                .collect();
            let ww: f64 = k.iter().sum();
            if ww != 0.0 {
                k.iter_mut().for_each(|v| *v /= ww);
            }
            let one = (1u32 << PRECISION_BITS) as f64;
            let kk = k.iter().map(|&p| if p < 0.0 { (-0.5 + p * one) as i32 } else { (0.5 + p * one) as i32 }).collect();
            (xmin, kk)
        })
        .collect()
}

fn clip8(v: i32) -> u8 {
    (v >> PRECISION_BITS).clamp(0, 255) as u8
}

/// One pass along axis 1 (x) or 0 (y), as Pillow's ImagingResampleHorizontal/Vertical_8bpc.
fn pass(a: &Array3<u8>, out_size: usize, axis: usize) -> Array3<u8> {
    let (h, w, c) = a.dim();
    let n = if axis == 1 { w } else { h };
    let k = coeffs(n, out_size);
    let shape = if axis == 1 { (h, out_size, c) } else { (out_size, w, c) };
    Array3::from_shape_fn(shape, |(y, x, ch)| {
        let (xmin, kk) = if axis == 1 { &k[x] } else { &k[y] };
        let mut ss: i32 = 1 << (PRECISION_BITS - 1);
        for (i, &kv) in kk.iter().enumerate() {
            let v = if axis == 1 { a[[y, xmin + i, ch]] } else { a[[xmin + i, x, ch]] };
            ss += v as i32 * kv;
        }
        clip8(ss)
    })
}

fn muldiv255(a: u8, b: u8) -> u8 {
    let t = a as u32 * b as u32 + 128;
    (((t >> 8) + t) >> 8) as u8
}

/// img.resize((w, h), Image.BOX) for any channel count; RGBA and LA are premultiplied around it as Pillow does.
pub fn resize_box(a: &ArrayView3<u8>, w: usize, h: usize) -> Array3<u8> {
    let (ih, iw, c) = a.dim();
    let alpha = c == 4 || c == 2;
    let mut src = a.to_owned();
    if (ih, iw) == (h, w) {
        return src;
    }
    if alpha {
        for mut p in src.lanes_mut(ndarray::Axis(2)) {
            let al = p[c - 1];
            for k in 0..c - 1 {
                p[k] = muldiv255(p[k], al);
            }
        }
    }
    let mut out = if iw != w { pass(&src, w, 1) } else { src };
    if ih != h {
        out = pass(&out, h, 0);
    }
    if alpha {
        for mut p in out.lanes_mut(ndarray::Axis(2)) {
            let al = p[c - 1] as u32;
            if al != 0 && al != 255 {
                for k in 0..c - 1 {
                    p[k] = ((255 * p[k] as u32) / al).min(255) as u8;
                }
            }
        }
    }
    out
}

/// img.resize((w * k, h * k), Image.NEAREST): every pixel repeated k times across and down.
pub fn zoom(a: &Array3<u8>, k: usize) -> Array3<u8> {
    let (h, w, c) = a.dim();
    Array3::from_shape_fn((h * k, w * k, c), |(y, x, ch)| a[[y / k, x / k, ch]])
}

/// Equal cells laid in rows of `cols`, row-major: np.concatenate([np.concatenate(cells[i:i + cols], 1) for i in
/// range(0, len(cells) - len(cells) % cols, cols)], 0). A last row short of `cols` is left out.
pub fn tile(cells: &[Array3<u8>], cols: usize) -> Array3<u8> {
    let (h, w, c) = cells[0].dim();
    let rows = cells.len() / cols;
    let mut out = Array3::zeros((rows * h, cols * w, c));
    for (i, cell) in cells.iter().take(rows * cols).enumerate() {
        let (y, x) = (i / cols * h, i % cols * w);
        out.slice_mut(s![y..y + h, x..x + w, ..]).assign(cell);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zoom_and_tile() {
        let a = Array3::from_shape_fn((2, 3, 1), |(y, x, _)| (y * 3 + x) as u8);
        let z = zoom(&a, 2);
        assert_eq!(z.dim(), (4, 6, 1));
        assert_eq!((z[[3, 5, 0]], z[[1, 2, 0]]), (5, 1));
        let t = tile(&[a.clone(), z.slice(s![..2, ..3, ..]).to_owned(), a.clone()], 2);
        assert_eq!(t.dim(), (2, 6, 1));
        assert_eq!(t[[1, 5, 0]], 1);
    }

    fn fx(name: &str) -> std::path::PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/img").join(name)
    }

    #[test]
    fn converts_like_pil() {
        assert_eq!(read(fx("gray_trns.png")).unwrap(), read_raw(fx("gray_trns_rgba.png")).unwrap());
        assert_eq!(read(fx("la.png")).unwrap(), read_raw(fx("la_rgba.png")).unwrap());
        assert_eq!(read(fx("pal.png")).unwrap(), read_raw(fx("pal_rgba.png")).unwrap());
        // PIL keeps the transparency as an RGB tRNS on save, so the expected file reads back with alpha
        assert_eq!(read_rgb(fx("pal.png")).unwrap(), read_rgb(fx("pal_rgb.png")).unwrap());
        assert_eq!(read_rgb(fx("rgba.png")).unwrap(), read_raw(fx("rgb.png")).unwrap());
    }

    #[test]
    fn box_resize_matches_pillow() {
        for mode in ["rgba", "rgb"] {
            let src = read_raw(fx(&format!("{mode}.png"))).unwrap();
            for (w, h) in [(10, 7), (40, 30), (23, 5), (7, 17), (3, 2), (50, 9)] {
                let want = read_raw(fx(&format!("{mode}_box_{w}x{h}.png"))).unwrap();
                let got = resize_box(&src.view(), w, h);
                let bad = got.iter().zip(want.iter()).filter(|(a, b)| a != b).count();
                assert_eq!(bad, 0, "{mode} {w}x{h}: {bad} values differ");
            }
        }
    }

    #[test]
    fn writes_and_reads_back() {
        let dir = std::env::temp_dir().join("beanfx_img_test");
        std::fs::create_dir_all(&dir).unwrap();
        let a = read(fx("rgba.png")).unwrap();
        write(dir.join("a.png"), &a.view()).unwrap();
        assert_eq!(read_raw(dir.join("a.png")).unwrap(), a);
        let b = convert_rgb(&a.view()).unwrap();
        write(dir.join("b.png"), &b.view()).unwrap();
        assert_eq!(read_raw(dir.join("b.png")).unwrap(), b);
    }
}
