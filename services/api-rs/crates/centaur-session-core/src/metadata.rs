use serde_json::Value;

pub fn empty_object() -> Value {
    Value::Object(serde_json::Map::new())
}
