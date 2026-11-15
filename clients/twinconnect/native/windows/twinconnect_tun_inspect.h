#pragma once
#include <flutter/encodable_value.h>

// Implemented in a separate native Windows translation unit so that IP
// Helper API headers receive the correct Windows target macros before any
// Flutter runner header has been included.
namespace twinconnect_tun_inspect {
flutter::EncodableValue Inspect();
}
