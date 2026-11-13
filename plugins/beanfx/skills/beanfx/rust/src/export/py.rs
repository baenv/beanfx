//! Python-compatible text: float repr, str repr, str() of a JSON value, json.dumps layout, rounding, equality.

use serde_json::Value;

/// repr(float): the shortest round-trip digits, exponent form past 1e16 or below 1e-4.
pub fn float_repr(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.into();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0.0" } else { "0.0" }.into();
    }
    let sign = if x < 0.0 { "-" } else { "" };
    let s = format!("{:e}", x.abs());
    let (mant, exp) = s.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let digits: String = mant.chars().filter(|c| *c != '.').collect();
    let decpt = exp + 1;
    let body = if -4 < decpt && decpt <= 16 {
        let n = digits.len() as i32;
        if decpt <= 0 {
            format!("0.{}{}", "0".repeat((-decpt) as usize), digits)
        } else if decpt >= n {
            format!("{}{}.0", digits, "0".repeat((decpt - n) as usize))
        } else {
            format!("{}.{}", &digits[..decpt as usize], &digits[decpt as usize..])
        }
    } else {
        let m = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits.clone() };
        format!("{}e{}{:02}", m, if exp < 0 { '-' } else { '+' }, exp.abs())
    };
    format!("{sign}{body}")
}

/// repr(str).
pub fn str_repr(s: &str) -> String {
    let q = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut o = String::from(q);
    for c in s.chars() {
        match c {
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            c if c == q => {
                o.push('\\');
                o.push(c)
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => o.push_str(&format!("\\x{:02x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push(q);
    o
}

/// str(value) of a JSON value read as the Python object it came from.
pub fn show(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) => match n.as_i64() {
            Some(i) => i.to_string(),
            None => match n.as_u64() {
                Some(u) => u.to_string(),
                None => float_repr(n.as_f64().unwrap_or(f64::NAN)),
            },
        },
        Value::String(s) => s.clone(),
        Value::Array(a) => format!("[{}]", a.iter().map(repr).collect::<Vec<_>>().join(", ")),
        Value::Object(m) => {
            format!("{{{}}}", m.iter().map(|(k, x)| format!("{}: {}", str_repr(k), repr(x))).collect::<Vec<_>>().join(", "))
        }
    }
}

/// repr(value).
pub fn repr(v: &Value) -> String {
    match v {
        Value::String(s) => str_repr(s),
        _ => show(v),
    }
}

/// repr of a tuple of strings.
pub fn tuple_repr(items: &[&str]) -> String {
    let parts: Vec<String> = items.iter().map(|s| str_repr(s)).collect();
    if parts.len() == 1 {
        format!("({},)", parts[0])
    } else {
        format!("({})", parts.join(", "))
    }
}

/// f"{x:.0f}": round half to even on the exact value.
pub fn fmt0(x: f64) -> String {
    format!("{}", x.round_ties_even() as i64)
}

/// round(x, n) for a float: correctly rounded decimal, ties to even.
pub fn round_n(x: f64, n: usize) -> f64 {
    format!("{:.*}", n, x).parse().unwrap_or(x)
}

pub fn truth(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(true),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(m) => !m.is_empty(),
    }
}

/// Python ==: 1 == 1.0 == True, dicts ignore order.
pub fn eq(a: &Value, b: &Value) -> bool {
    let num = |v: &Value| match v {
        Value::Bool(x) => Some(if *x { 1.0 } else { 0.0 }),
        Value::Number(n) => n.as_f64(),
        _ => None,
    };
    match (a, b) {
        (Value::Null, Value::Null) => true,
        (Value::String(x), Value::String(y)) => x == y,
        (Value::Array(x), Value::Array(y)) => x.len() == y.len() && x.iter().zip(y).all(|(p, q)| eq(p, q)),
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).map(|w| eq(v, w)).unwrap_or(false))
        }
        _ => match (a, b) {
            (Value::Number(x), Value::Number(y)) if x.is_i64() && y.is_i64() => x.as_i64() == y.as_i64(),
            _ => matches!((num(a), num(b)), (Some(x), Some(y)) if x == y),
        },
    }
}

fn esc(s: &str, o: &mut String) {
    o.push('"');
    for c in s.chars() {
        match c {
            '"' => o.push_str("\\\""),
            '\\' => o.push_str("\\\\"),
            '\n' => o.push_str("\\n"),
            '\r' => o.push_str("\\r"),
            '\t' => o.push_str("\\t"),
            '\u{8}' => o.push_str("\\b"),
            '\u{c}' => o.push_str("\\f"),
            ' '..='~' => o.push(c),
            c => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    o.push_str(&format!("\\u{:04x}", u));
                }
            }
        }
    }
    o.push('"');
}

fn dump(v: &Value, indent: Option<usize>, level: usize, o: &mut String) {
    let (nl, pad_in, pad_out) = match indent {
        Some(n) => ("\n".to_string(), " ".repeat(n * (level + 1)), " ".repeat(n * level)),
        None => (String::new(), String::new(), String::new()),
    };
    let sep = if indent.is_some() { "," } else { ", " };
    match v {
        Value::Null => o.push_str("null"),
        Value::Bool(b) => o.push_str(if *b { "true" } else { "false" }),
        Value::Number(_) => match v {
            Value::Number(n) if n.is_f64() => o.push_str(&float_repr(n.as_f64().unwrap())),
            _ => o.push_str(&show(v)),
        },
        Value::String(s) => esc(s, o),
        Value::Array(a) if a.is_empty() => o.push_str("[]"),
        Value::Array(a) => {
            o.push('[');
            o.push_str(&nl);
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    o.push_str(sep);
                    o.push_str(&nl);
                }
                o.push_str(&pad_in);
                dump(x, indent, level + 1, o);
            }
            o.push_str(&nl);
            o.push_str(&pad_out);
            o.push(']');
        }
        Value::Object(m) if m.is_empty() => o.push_str("{}"),
        Value::Object(m) => {
            o.push('{');
            o.push_str(&nl);
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    o.push_str(sep);
                    o.push_str(&nl);
                }
                o.push_str(&pad_in);
                esc(k, o);
                o.push_str(": ");
                dump(x, indent, level + 1, o);
            }
            o.push_str(&nl);
            o.push_str(&pad_out);
            o.push('}');
        }
    }
}

/// json.dumps(v, indent=indent) with the default separators and ensure_ascii.
pub fn dumps(v: &Value, indent: Option<usize>) -> String {
    let mut o = String::new();
    dump(v, indent, 0, &mut o);
    o
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn floats_read_like_python() {
        let cases = [(1.0, "1.0"), (0.1, "0.1"), (2.5e-5, "2.5e-05"), (1e16, "1e+16"), (123456789012345.0, "123456789012345.0"),
                     (0.0001, "0.0001"), (-0.5, "-0.5"), (1.5e300, "1.5e+300"), (0.333333333333333, "0.333333333333333")];
        for (x, s) in cases {
            assert_eq!(float_repr(x), s);
        }
    }

    #[test]
    fn dumps_matches_indent_one() {
        let v = json!({"a": [1, 2.0, "x\u{e9}"], "b": {}, "c": [], "d": null, "e": true});
        let want = "{\n \"a\": [\n  1,\n  2.0,\n  \"x\\u00e9\"\n ],\n \"b\": {},\n \"c\": [],\n \"d\": null,\n \"e\": true\n}";
        assert_eq!(dumps(&v, Some(1)), want);
        assert_eq!(dumps(&json!({"a": [1, 2], "b": "c"}), None), "{\"a\": [1, 2], \"b\": \"c\"}");
    }

    #[test]
    fn reprs_and_rounding() {
        assert_eq!(str_repr("it's"), "\"it's\"");
        assert_eq!(str_repr("dance"), "'dance'");
        assert_eq!(fmt0(2.5), "2");
        assert_eq!(fmt0(3.5), "4");
        assert_eq!(round_n(0.03125, 4), 0.0312);
        assert_eq!(round_n(0.3, 4), 0.3);
        assert!(eq(&json!(1), &json!(1.0)) && !eq(&json!("a"), &json!(1)));
    }
}
