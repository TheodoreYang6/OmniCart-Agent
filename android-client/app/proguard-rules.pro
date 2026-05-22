# OmniCart Agent ProGuard Rules
# V0-Android: minimal rules, no obfuscation needed for demo

# Retrofit
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.omnicart.agent.core.model.** { *; }

# Gson
-keep class com.google.gson.** { *; }
-keepattributes EnclosingMethod
