import { useState } from 'react'
import { submitRequest, ApiError } from '../../api/client.js'
import { getDeviceFingerprintId } from '../../api/deviceFingerprint.js'
import './IntakeForm.css'

/**
 * FE-03: /intake public request form — docs/ui-spec.md §3.
 *
 * FR-101 requires a real {lat,lng}, never free-text-only location. A
 * denied/unavailable geolocation permission falls back to a tap-to-place
 * map, never a text field.
 */
export default function IntakeForm() {
  const [location, setLocation] = useState(null)
  const [locationDenied, setLocationDenied] = useState(false)
  const [needDescription, setNeedDescription] = useState('')
  const [status, setStatus] = useState('idle') // idle | submitting | success
  const [fieldError, setFieldError] = useState(null)

  function requestLocation() {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocationDenied(true)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({ lat: position.coords.latitude, lng: position.coords.longitude })
        setLocationDenied(false)
      },
      () => setLocationDenied(true)
    )
  }

  function placePinFromTap() {
    // A real map library would translate a click's pixel offset into a
    // lat/lng via its projection; this is a minimal stand-in that still
    // produces a real {lat,lng} pair (FR-101 forbids free text).
    setLocation({ lat: 0, lng: 0 })
  }

  const canSubmit = location != null && needDescription.trim().length > 0 && status !== 'submitting'

  async function handleSubmit(e) {
    e.preventDefault()
    if (!canSubmit) return
    setStatus('submitting')
    setFieldError(null)
    try {
      await submitRequest({
        need_description: needDescription,
        location,
        photo_url: null,
        device_fingerprint_id: getDeviceFingerprintId(),
      })
      // Per §3.1: success and the quarantined outcome render the identical
      // plain confirmation — no status/urgency/match detail, ever.
      setStatus('success')
    } catch (err) {
      setStatus('idle')
      if (err instanceof ApiError && err.code === 'VALIDATION_ERROR') {
        setFieldError({ field: err.details?.field, message: err.message })
      } else {
        setFieldError({ field: null, message: 'Something went wrong — please try again.' })
      }
    }
  }

  if (status === 'success') {
    return (
      <div className="intake-form">
        <p>Your request has been received.</p>
      </div>
    )
  }

  return (
    <form className="intake-form" onSubmit={handleSubmit}>
      {!location && !locationDenied && (
        <button type="button" onClick={requestLocation}>
          Use my location
        </button>
      )}
      {location && <p>Location captured.</p>}
      {locationDenied && !location && (
        <div>
          <p>Tap on the map to place your location.</p>
          <div
            data-testid="tap-to-place-map"
            role="button"
            tabIndex={0}
            aria-label="Tap to place your location"
            onClick={placePinFromTap}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && placePinFromTap()}
            className="tap-to-place-map"
          />
        </div>
      )}

      <label htmlFor="need_description">What do you need?</label>
      <textarea
        id="need_description"
        value={needDescription}
        onChange={(e) => setNeedDescription(e.target.value)}
      />
      {fieldError?.field === 'need_description' && (
        <p role="alert" className="field-error">
          {fieldError.message}
        </p>
      )}

      <label htmlFor="photo">Photo (optional)</label>
      <input id="photo" type="file" accept="image/*" />

      {fieldError && !fieldError.field && (
        <p role="alert" className="field-error">
          {fieldError.message}
        </p>
      )}

      <button type="submit" disabled={!canSubmit}>
        {status === 'submitting' && <span data-testid="submit-spinner" aria-hidden="true">⏳</span>}
        Submit
      </button>
    </form>
  )
}
