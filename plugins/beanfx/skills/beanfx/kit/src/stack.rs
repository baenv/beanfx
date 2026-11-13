//! Frame stacks: what the writers and checks take (a list of frames, or a list of rows of them, one row per heading)
//! and the flat block they work on inside.

use ndarray::Array3;

/// A list of equal (h, w, c) frames, or rows of such lists (one row per heading). Build it with `.into()` from
/// `&[Array3<T>]`, `&Vec<Array3<T>>`, `&[Vec<Array3<T>>]` or `&Vec<Vec<Array3<T>>>`.
#[derive(Clone, Copy)]
pub enum Stack<'a, T> {
    Flat(&'a [Array3<T>]),
    Rows(&'a [Vec<Array3<T>>]),
}

impl<'a, T> From<&'a [Array3<T>]> for Stack<'a, T> {
    fn from(f: &'a [Array3<T>]) -> Self {
        Stack::Flat(f)
    }
}
impl<'a, T> From<&'a Vec<Array3<T>>> for Stack<'a, T> {
    fn from(f: &'a Vec<Array3<T>>) -> Self {
        Stack::Flat(f)
    }
}
impl<'a, T, const N: usize> From<&'a [Array3<T>; N]> for Stack<'a, T> {
    fn from(f: &'a [Array3<T>; N]) -> Self {
        Stack::Flat(f)
    }
}
impl<'a, T> From<&'a [Vec<Array3<T>>]> for Stack<'a, T> {
    fn from(f: &'a [Vec<Array3<T>>]) -> Self {
        Stack::Rows(f)
    }
}
impl<'a, T> From<&'a Vec<Vec<Array3<T>>>> for Stack<'a, T> {
    fn from(f: &'a Vec<Vec<Array3<T>>>) -> Self {
        Stack::Rows(f)
    }
}

impl<'a, T> Stack<'a, T> {
    /// Every frame, row-major.
    pub fn flat(&self) -> Vec<&'a Array3<T>> {
        match *self {
            Stack::Flat(f) => f.iter().collect(),
            Stack::Rows(r) => r.iter().flat_map(|row| row.iter()).collect(),
        }
    }

    /// (rows, frames per row).
    pub fn dims(&self) -> (usize, usize) {
        match *self {
            Stack::Flat(f) => (1, f.len()),
            Stack::Rows(r) => (r.len(), r.first().map(Vec::len).unwrap_or(0)),
        }
    }
}

/// The light of a sheet: frames of u8 (0..255) or f64 (0..1), (h, w, 3) or more channels.
#[derive(Clone, Copy)]
pub enum Light<'a> {
    U8(Stack<'a, u8>),
    F64(Stack<'a, f64>),
}

macro_rules! light_from {
    ($t:ty, $v:ident, $e:ident) => {
        impl<'a> From<$t> for Light<'a> {
            fn from(f: $t) -> Self {
                Light::$v(Stack::from(f))
            }
        }
    };
}
light_from!(&'a [Array3<u8>], U8, x);
light_from!(&'a Vec<Array3<u8>>, U8, x);
light_from!(&'a [Vec<Array3<u8>>], U8, x);
light_from!(&'a Vec<Vec<Array3<u8>>>, U8, x);
light_from!(&'a [Array3<f64>], F64, x);
light_from!(&'a Vec<Array3<f64>>, F64, x);
light_from!(&'a [Vec<Array3<f64>>], F64, x);
light_from!(&'a Vec<Vec<Array3<f64>>>, F64, x);

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Data {
    U8(Vec<u8>),
    F64(Vec<f64>),
}

/// A C-order block: shape (rows, n, h, w, c) or (n, h, w, c), u8 or f64.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Array {
    pub shape: Vec<usize>,
    pub data: Data,
}

impl Array {
    pub fn len(&self) -> usize {
        self.shape.iter().product()
    }
    pub fn is_u8(&self) -> bool {
        matches!(self.data, Data::U8(_))
    }
    /// The data as u8; panics for f64 (callers check is_u8 first).
    pub fn as_u8(&self) -> &[u8] {
        match &self.data {
            Data::U8(v) => v,
            _ => panic!("array is not u8"),
        }
    }
    /// Every value as f64 (u8 stays 0..255, no scaling).
    pub fn to_f64(&self) -> Vec<f64> {
        match &self.data {
            Data::U8(v) => v.iter().map(|&x| x as f64).collect(),
            Data::F64(v) => v.clone(),
        }
    }
}

fn shape_of<T>(s: &Stack<T>) -> Result<Vec<usize>, String> {
    let flat = s.flat();
    let first = flat.first().ok_or("no frames")?;
    let (h, w, c) = first.dim();
    if flat.iter().any(|f| f.dim() != (h, w, c)) {
        return Err("frames differ in shape".into());
    }
    let (r, n) = s.dims();
    if let Stack::Rows(rows) = s {
        if rows.iter().any(|row| row.len() != n) {
            return Err("rows differ in length".into());
        }
    }
    Ok(match s {
        Stack::Flat(_) => vec![n, h, w, c],
        Stack::Rows(_) => vec![r, n, h, w, c],
    })
}

fn gather<T: Copy>(s: &Stack<T>) -> Vec<T> {
    let mut out = vec![];
    for f in s.flat() {
        match f.as_slice() {
            Some(sl) => out.extend_from_slice(sl),
            None => out.extend(f.iter().copied()),
        }
    }
    out
}

pub(crate) fn block_u8(s: Stack<u8>) -> Result<Array, String> {
    Ok(Array { shape: shape_of(&s)?, data: Data::U8(gather(&s)) })
}

pub(crate) fn block_light(l: Light) -> Result<Array, String> {
    match l {
        Light::U8(s) => block_u8(s),
        Light::F64(s) => Ok(Array { shape: shape_of(&s)?, data: Data::F64(gather(&s)) }),
    }
}

/// Frames of a (n, h, w, c) u8 block as arrays.
pub(crate) fn unblock(n: usize, h: usize, w: usize, c: usize, data: Vec<u8>) -> Vec<Array3<u8>> {
    let sz = h * w * c;
    (0..n).map(|i| Array3::from_shape_vec((h, w, c), data[i * sz..(i + 1) * sz].to_vec()).unwrap()).collect()
}
