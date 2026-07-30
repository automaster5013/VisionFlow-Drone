FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /workspace

COPY . .
RUN sed -i 's/\r$//' gradlew \
    && chmod +x gradlew \
    && ./gradlew clean bootJar --no-daemon \
    && cp "$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' -print -quit)" /tmp/app.jar

FROM eclipse-temurin:21-jre-alpine AS runner
WORKDIR /app

RUN apk add --no-cache curl \
    && addgroup -S visionflow \
    && adduser -S visionflow -G visionflow \
    && mkdir -p /app/data \
    && chown -R visionflow:visionflow /app

COPY --from=builder --chown=visionflow:visionflow /tmp/app.jar /app/app.jar

USER visionflow
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75.0", "-jar", "/app/app.jar"]
