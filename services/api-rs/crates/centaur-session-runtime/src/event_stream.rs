use std::{collections::VecDeque, time::Duration};

use centaur_session_core::{SessionEvent, ThreadKey};
use centaur_session_sqlx::{PgSessionStore, SessionEventListener};
use futures_util::{Stream, stream};
use tokio::time::{Instant, Interval, MissedTickBehavior, interval_at};

use crate::SessionRuntimeError;

const EVENT_STREAM_SAFETY_POLL_INTERVAL: Duration = Duration::from_secs(30);

struct EventStreamState {
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
    pending: VecDeque<SessionEvent>,
    listener: SessionEventListener,
    safety_tick: Interval,
    done: bool,
}

pub(crate) fn session_event_stream(
    store: PgSessionStore,
    thread_key: ThreadKey,
    after_event_id: i64,
    listener: SessionEventListener,
) -> impl Stream<Item = Result<SessionEvent, SessionRuntimeError>> {
    stream::unfold(
        EventStreamState {
            store,
            thread_key,
            after_event_id,
            pending: VecDeque::new(),
            listener,
            safety_tick: {
                let mut tick = interval_at(
                    Instant::now() + EVENT_STREAM_SAFETY_POLL_INTERVAL,
                    EVENT_STREAM_SAFETY_POLL_INTERVAL,
                );
                tick.set_missed_tick_behavior(MissedTickBehavior::Delay);
                tick
            },
            done: false,
        },
        |mut state| async move {
            loop {
                if let Some(event) = state.pending.pop_front() {
                    state.after_event_id = event.event_id;
                    return Some((Ok(event), state));
                }
                if state.done {
                    return None;
                }
                match state
                    .store
                    .list_events_after(&state.thread_key, state.after_event_id, 100)
                    .await
                {
                    Ok(events) if events.is_empty() => loop {
                        tokio::select! {
                            notification = state.listener.recv() => {
                                match notification {
                                    Ok(notification)
                                        if notification.thread_key == state.thread_key.as_str()
                                            && notification.event_id > state.after_event_id =>
                                    {
                                        break;
                                    }
                                    Ok(_) => {}
                                    Err(error) => {
                                        state.done = true;
                                        return Some((Err(SessionRuntimeError::Store(error)), state));
                                    }
                                }
                            }
                            _ = state.safety_tick.tick() => break,
                        }
                    },
                    Ok(events) => state.pending = events.into(),
                    Err(error) => {
                        state.done = true;
                        return Some((Err(SessionRuntimeError::Store(error)), state));
                    }
                }
            }
        },
    )
}
