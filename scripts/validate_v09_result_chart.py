from pathlib import Path

m=Path('app/src/main/java/com/mh/analysis/MainActivityV29.kt').read_text()
h=Path('app/src/main/assets/fcs_chart.html').read_text()
b=Path('app/build.gradle.kts').read_text()

checks={
    'V.09 header':'MH - V.09' in m,
    'organized true HTF':'➜ TRUE HTF' in m,
    'organized execution/news':'➜ EXECUTION / NEWS' in m,
    'organized calibration':'➜ CALIBRATION' in m,
    'compact decision filter':'private fun compactDecision' in m,
    'parent scroll interception blocked':'requestDisallowInterceptTouchEvent(true)' in m,
    'touch release restored':'requestDisallowInterceptTouchEvent(false)' in m,
    'levels toggle button':'LEVELS ON' in h and 'LEVELS OFF' in h,
    'levels active state':'syncLevelsButton' in h,
    'long press jitter tolerance':'travel>8' in h,
    'touch cancel handled':"touchcancel" in h,
    'pinch chart preserved':'pinchDist' in h,
    'pan chart preserved':'offset+=-dx/step' in h,
    'crosshair preserved':'cross={x,y}' in h,
    'entry levels preserved':"'entry','#f2c94c','ENTRY'" in h,
    'V.09 version':'versionName = "V.09"' in b and 'versionCode = 41' in b,
}
failed=[k for k,v in checks.items() if not v]
if failed:
    raise SystemExit('V.09 validation failed: '+', '.join(failed))
print('V.09 result organization/chart gesture validation passed')
