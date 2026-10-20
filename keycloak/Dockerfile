# syntax=docker/dockerfile:1
# Imagem de produção: build otimizado (sobe em segundos, não em dezenas) com o
# tema embutido. Hostname, banco e segredos entram em tempo de execução.
FROM quay.io/keycloak/keycloak:26.4.7 AS construtor
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true
COPY themes/fisioagenda /opt/keycloak/themes/fisioagenda
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.4.7
COPY --from=construtor /opt/keycloak/ /opt/keycloak/
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
