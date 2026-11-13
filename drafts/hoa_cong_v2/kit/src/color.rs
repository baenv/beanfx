//! Colour helpers shared by the kit: hex colour text to channels.

/// #rgb, #rgba, #rrggbb or #rrggbbaa (the # optional) as r, g, b, a; alpha 255 when absent (pfx._hexa).
pub fn hexa(s: &str) -> Result<[u8; 4], String> {
    let mut t: String = s.trim_start_matches('#').to_string();
    if t.len() == 3 || t.len() == 4 {
        t = t.chars().flat_map(|c| [c, c]).collect();
    }
    if (t.len() != 6 && t.len() != 8) || !t.is_ascii() {
        return Err(format!("bad hex colour {s}"));
    }
    let mut out = [0, 0, 0, 255];
    for (k, o) in out.iter_mut().enumerate().take(t.len() / 2) {
        *o = u8::from_str_radix(&t[2 * k..2 * k + 2], 16).map_err(|_| format!("bad hex colour {s}"))?;
    }
    Ok(out)
}

/// #rrggbb (or #rgb) as r, g, b.
pub fn rgb(s: &str) -> Result<[u8; 3], String> {
    let [r, g, b, _] = hexa(s)?;
    Ok([r, g, b])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_every_form() {
        assert_eq!(hexa("#101018").unwrap(), [16, 16, 24, 255]);
        assert_eq!(hexa("fa0").unwrap(), [255, 170, 0, 255]);
        assert_eq!(hexa("#ff000080").unwrap(), [255, 0, 0, 128]);
        assert_eq!(rgb("#0a0b0c").unwrap(), [10, 11, 12]);
        assert!(hexa("#12345").is_err());
    }
}
