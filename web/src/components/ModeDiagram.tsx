import type { Mode } from '../types'
import styles from './ModeDiagram.module.css'

interface Props {
  mode: Mode | null
  connected: boolean
  clientId: string | null
  cloudSince: number | null
  azureIp: string | null
}

export default function ModeDiagram({ mode, connected, clientId, cloudSince, azureIp }: Props) {
  const bridge = mode === 'bridge'
  const listen = mode === 'listen'
  const raw = mode === 'raw'
  const cloudUp = cloudSince != null

  return (
    <div className={styles.wrap}>
      <div className={styles.flow}>
        {/* BOX */}
        <div className={styles.node + ' ' + (connected ? styles.highlight : styles.muted)}>
          <span className={styles.icon}>📦</span>
          <span className={styles.name}>Box</span>
          <span className={styles.sub}>
            {connected ? clientId ?? 'Box' : 'hors ligne'}
          </span>
        </div>

        {/* BOX -> BRIDGE */}
        <div
          className={
            styles.seg +
            (bridge || raw ? styles.live : connected ? styles.live : styles.muted)
          }
        >
          <span className={styles.arrow}>▶</span>
          <span className={styles.seglab}>
            {raw ? 'broker MQTT' : bridge ? 'MQTT TLS :8883' : 'MQTT TLS :8883'}
          </span>
        </div>

        {raw ? (
          <>
            {/* BROKER (raw) */}
            <div className={styles.node + ' ' + styles.highlight}>
              <span className={styles.icon}>🏠</span>
              <span className={styles.name}>Broker MQTT local</span>
              <span className={styles.sub}>{connected ? 'connecté' : 'hors ligne'}</span>
            </div>

            {/* BROKER -> BRIDGE (subscribe/events) */}
            <div className={styles.seg + (connected ? styles.live : styles.muted)}>
              <span className={styles.arrow}>▶</span>
              <span className={styles.seglab}>événements / commandes</span>
            </div>

            {/* BRIDGE (raw client) */}
            <div className={styles.node}>
              <span className={styles.icon}>⚙️</span>
              <span className={styles.name}>Aldes Bridge</span>
              <span className={styles.sub}>client MQTT natif</span>
            </div>
          </>
        ) : (
          <>
            {/* BRIDGE */}
            <div className={styles.node + ' ' + (bridge || listen ? styles.highlight : '')}>
              <span className={styles.icon}>⚙️</span>
              <span className={styles.name}>Aldes Bridge</span>
              <span className={styles.sub}>{bridge ? 'mode bridge' : listen ? 'mode listen' : 'mode proxy'}</span>
            </div>

            {/* BRIDGE -> AZURE (proxy & listen) */}
            <div className={styles.seg + (bridge ? styles.off : cloudUp ? styles.live : styles.warning)}>
              <span className={styles.arrow}>▶</span>
              <span className={styles.seglab}>{bridge ? 'inactif' : listen ? 'relai télémétrie' : 'relai'}</span>
            </div>

            {/* AZURE */}
            <div className={styles.node + (bridge ? styles.muted : cloudUp ? styles.active : styles.warn)}>
              <span className={styles.icon}>☁️</span>
              <span className={styles.name}>Azure</span>
              <span className={styles.sub}>
                {bridge ? 'décroché' : cloudUp ? 'connecté' : 'déconnecté'}
              </span>
              {azureIp && (
                <span className={styles.ip + (cloudUp ? '' : ' ' + styles.ipWarn)}>{azureIp}</span>
              )}
            </div>
          </>
        )}
      </div>

      <p className={styles.explain}>
        {bridge ? (
          <>
            <strong>Bridge</strong> : la box se connecte <em>directement au bridge</em>,
            qui termine la connexion. Azure est <strong>ignoré</strong> — on lit / on
            commande la box localement, sans passer par le cloud.
          </>
        ) : raw ? (
          <>
            <strong>Natif (raw)</strong> : le bridge joue le rôle de <em>client MQTT</em> et
            se connecte au broker configuré. On lit les <em>événements</em> de la box (topic{' '}
            <code>evt_topic</code>) et on envoie des <em>commandes</em> (topic{' '}
            <code>cmd_topic</code>).
          </>
        ) : listen ? (
          <>
            <strong>Listen</strong> : comme le proxy, la box rejoint Azure via le bridge et
            sa <em>télémétrie remonte</em> vers le cloud. Mais les commandes{' '}
            <strong>Azure → box</strong> sont <strong>bloquées</strong> : observées et
            journalisées, jamais transmises à la box. L‘injection locale depuis la WebUI
            reste possible.
          </>
        ) : (
          <>
            <strong>Proxy</strong> : la box passe par le bridge <em>pour rejoindre Azure</em>.
            Le bridge relaie tout (on reste « invisible » côté cloud) et permet d‘observer /
            d‘injecter les commandes au passage.
          </>
        )}
      </p>
    </div>
  )
}