use std::time::Duration;

use crate::SessionRuntimeError;

pub(crate) fn validate_input_lines(lines: &[String]) -> Result<(), SessionRuntimeError> {
    for (index, line) in lines.iter().enumerate() {
        if line.contains('\n') || line.contains('\r') {
            return Err(SessionRuntimeError::BadRequest(format!(
                "input_lines[{index}] must be one line"
            )));
        }
    }
    Ok(())
}

pub(crate) fn validate_duration_options(
    idle_timeout_ms: Option<u64>,
    max_duration_ms: Option<u64>,
) -> Result<(), SessionRuntimeError> {
    let idle_timeout = idle_timeout_ms.map(nonzero_duration_millis).transpose()?;
    let max_duration = max_duration_ms.map(nonzero_duration_millis).transpose()?;

    if let (Some(idle_timeout), Some(max_duration)) = (idle_timeout, max_duration)
        && idle_timeout > max_duration
    {
        return Err(SessionRuntimeError::BadRequest(
            "idle_timeout_ms must be less than or equal to max_duration_ms".to_owned(),
        ));
    }

    Ok(())
}

fn nonzero_duration_millis(value: u64) -> Result<Duration, SessionRuntimeError> {
    if value == 0 {
        return Err(SessionRuntimeError::BadRequest(
            "duration values must be greater than zero".to_owned(),
        ));
    }
    Ok(Duration::from_millis(value))
}
