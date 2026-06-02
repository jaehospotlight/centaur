use serde::Deserialize;
use sqlx::postgres::PgListener;

use crate::SessionStoreError;

pub const SESSION_EVENTS_CHANNEL: &str = "centaur_session_events";

pub struct SessionEventListener {
    pub(crate) listener: PgListener,
}

impl SessionEventListener {
    pub async fn recv(&mut self) -> Result<SessionEventNotification, SessionStoreError> {
        loop {
            let notification = self.listener.recv().await?;
            if notification.channel() != SESSION_EVENTS_CHANNEL {
                continue;
            }

            let payload = notification.payload();
            return serde_json::from_str(payload).map_err(|error| {
                SessionStoreError::InvalidNotification {
                    channel: notification.channel().to_owned(),
                    payload: payload.to_owned(),
                    error,
                }
            });
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct SessionEventNotification {
    pub thread_key: String,
    pub event_id: i64,
}

#[cfg(test)]
mod tests {
    use super::SessionEventNotification;

    #[test]
    fn parses_session_event_notification_payload() {
        let notification: SessionEventNotification =
            serde_json::from_str(r#"{"thread_key":"cli:test","event_id":42}"#).unwrap();

        assert_eq!(
            notification,
            SessionEventNotification {
                thread_key: "cli:test".to_owned(),
                event_id: 42,
            }
        );
    }
}
