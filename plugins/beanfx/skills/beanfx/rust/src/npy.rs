//! The .npy format numpy writes with np.save: magic, a header dict, then the data in C order.
//! Only the dtypes the kit hands over: u1 (bool arrays arrive as u1), i4, i8, f4, f8, little endian.

use std::fs;
use std::path::Path;

#[derive(Clone, Debug, PartialEq)]
pub enum Data {
    U8(Vec<u8>),
    I64(Vec<i64>),
    F64(Vec<f64>),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Array {
    pub shape: Vec<usize>,
    pub data: Data,
}

impl Array {
    pub fn u8(shape: Vec<usize>, data: Vec<u8>) -> Array {
        Array { shape, data: Data::U8(data) }
    }
    pub fn f64(shape: Vec<usize>, data: Vec<f64>) -> Array {
        Array { shape, data: Data::F64(data) }
    }
    pub fn len(&self) -> usize {
        self.shape.iter().product()
    }
    pub fn is_u8(&self) -> bool {
        matches!(self.data, Data::U8(_))
    }
    /// The data as u8; panics for other dtypes (callers check is_u8 first).
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
            Data::I64(v) => v.iter().map(|&x| x as f64).collect(),
            Data::F64(v) => v.clone(),
        }
    }
}

fn header_field<'a>(h: &'a str, key: &str) -> Option<&'a str> {
    let at = h.find(&format!("'{key}'"))? + key.len() + 2;
    let rest = h[at..].trim_start().strip_prefix(':')?.trim_start();
    Some(rest)
}

pub fn parse(bytes: &[u8]) -> Result<Array, String> {
    if bytes.len() < 10 || &bytes[..6] != b"\x93NUMPY" {
        return Err("not an npy file".into());
    }
    let (hlen, start) = if bytes[6] == 1 {
        (u16::from_le_bytes([bytes[8], bytes[9]]) as usize, 10)
    } else {
        (u32::from_le_bytes([bytes[8], bytes[9], bytes[10], bytes[11]]) as usize, 12)
    };
    let h = std::str::from_utf8(&bytes[start..start + hlen]).map_err(|e| e.to_string())?;
    let descr = header_field(h, "descr").ok_or("npy: no descr")?;
    let descr = descr.trim_start_matches('\'');
    let descr = &descr[..descr.find('\'').ok_or("npy: bad descr")?];
    if header_field(h, "fortran_order").map(|v| v.starts_with("True")).unwrap_or(false) {
        return Err("npy: fortran order; save np.ascontiguousarray".into());
    }
    let sh = header_field(h, "shape").ok_or("npy: no shape")?;
    let sh = &sh[1..sh.find(')').ok_or("npy: bad shape")?];
    let shape: Vec<usize> = sh
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .map(|s| s.trim_end_matches('L').parse::<usize>().map_err(|e| e.to_string()))
        .collect::<Result<_, _>>()?;
    let raw = &bytes[start + hlen..];
    let n: usize = shape.iter().product();
    let take = |w: usize| -> Result<&[u8], String> {
        raw.get(..n * w).ok_or_else(|| format!("npy: {} bytes for {n} values of {w}", raw.len()))
    };
    let data = match descr {
        "|u1" | "|b1" | "<u1" => Data::U8(take(1)?.to_vec()),
        "<i4" => Data::I64(take(4)?.chunks_exact(4).map(|c| i32::from_le_bytes(c.try_into().unwrap()) as i64).collect()),
        "<i8" => Data::I64(take(8)?.chunks_exact(8).map(|c| i64::from_le_bytes(c.try_into().unwrap())).collect()),
        "<f4" => Data::F64(take(4)?.chunks_exact(4).map(|c| f32::from_le_bytes(c.try_into().unwrap()) as f64).collect()),
        "<f8" => Data::F64(take(8)?.chunks_exact(8).map(|c| f64::from_le_bytes(c.try_into().unwrap())).collect()),
        d => return Err(format!("npy: dtype {d} not handled")),
    };
    Ok(Array { shape, data })
}

pub fn read(path: &Path) -> Result<Array, String> {
    parse(&fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?)
}

pub fn encode(a: &Array) -> Vec<u8> {
    let descr = match a.data {
        Data::U8(_) => "|u1",
        Data::I64(_) => "<i8",
        Data::F64(_) => "<f8",
    };
    let shape = match a.shape.len() {
        1 => format!("({},)", a.shape[0]),
        _ => format!("({})", a.shape.iter().map(|s| s.to_string()).collect::<Vec<_>>().join(", ")),
    };
    let mut h = format!("{{'descr': '{descr}', 'fortran_order': False, 'shape': {shape}, }}");
    while (10 + h.len() + 1) % 64 != 0 {
        h.push(' ');
    }
    h.push('\n');
    let mut out = b"\x93NUMPY\x01\x00".to_vec();
    out.extend((h.len() as u16).to_le_bytes());
    out.extend(h.as_bytes());
    match &a.data {
        Data::U8(v) => out.extend(v),
        Data::I64(v) => v.iter().for_each(|x| out.extend(x.to_le_bytes())),
        Data::F64(v) => v.iter().for_each(|x| out.extend(x.to_le_bytes())),
    }
    out
}

pub fn write(path: &Path, a: &Array) -> Result<(), String> {
    fs::write(path, encode(a)).map_err(|e| format!("{}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let a = Array::u8(vec![2, 3], vec![1, 2, 3, 4, 5, 6]);
        assert_eq!(parse(&encode(&a)).unwrap(), a);
        let b = Array::f64(vec![4], vec![0.5, -1.0, 2.25, 0.0]);
        assert_eq!(parse(&encode(&b)).unwrap(), b);
    }
}
