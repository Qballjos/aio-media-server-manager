<script setup>
import { ref } from 'vue'

const props = defineProps({
  protocol: { type: String, default: 'wireguard' },
  path: { type: String, default: '' },
  text: { type: String, default: '' },
  hasConfig: { type: Boolean, default: false }
})
const emit = defineEmits(['update:protocol', 'update:path', 'update:text'])

const fileInput = ref(null)
const fileError = ref('')

function onFile(event) {
  fileError.value = ''
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > 256 * 1024) {
    fileError.value = 'Config file must be 256 KB or smaller.'
    return
  }
  const name = String(file.name || '').toLowerCase()
  if (name.endsWith('.ovpn')) emit('update:protocol', 'openvpn')
  const reader = new FileReader()
  reader.onload = () => {
    emit('update:text', String(reader.result || ''))
  }
  reader.onerror = () => {
    fileError.value = 'Could not read that file.'
  }
  reader.readAsText(file)
}
</script>

<template>
  <div class="vpn-config-fields">
    <label class="ui-field">
      <span>Protocol</span>
      <select class="ui-input" :value="protocol" @change="emit('update:protocol', $event.target.value)">
        <option value="wireguard">WireGuard</option>
        <option value="openvpn">OpenVPN</option>
      </select>
    </label>
    <p class="vpn-hint">Upload a provider profile or paste it. It is stored as {{ protocol === 'openvpn' ? 'client.ovpn' : 'wg0.conf' }} under the config VPN folder unless you set a path.</p>
    <p v-if="hasConfig" class="vpn-hint">A config file is already saved{{ path ? ` at ${path}` : '' }}.</p>
    <label class="ui-field">
      <span>Upload config</span>
      <input ref="fileInput" class="vpn-file" type="file" accept=".conf,.ovpn,.txt,text/plain" @change="onFile" />
    </label>
    <p v-if="fileError" class="vpn-hint">{{ fileError }}</p>
    <label class="ui-field">
      <span>Paste config</span>
      <textarea
        class="ui-input font-mono"
        rows="8"
        :value="text"
        :placeholder="hasConfig ? 'Leave blank to keep the saved file' : protocol === 'openvpn' ? 'client\ndev tun\nremote …' : '[Interface]\nPrivateKey = …\nAddress = …\n\n[Peer]\n…'"
        @input="emit('update:text', $event.target.value)"
      />
    </label>
    <label class="ui-field">
      <span>Save as (optional)</span>
      <input
        class="ui-input font-mono"
        :value="path"
        :placeholder="protocol === 'openvpn' ? '/config/vpn/client.ovpn' : '/config/vpn/wg0.conf'"
        @input="emit('update:path', $event.target.value)"
      />
    </label>
  </div>
</template>

<style scoped>
.vpn-config-fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.vpn-file {
  color: #cbd5e1;
  font-size: 0.85rem;
}
.vpn-hint {
  margin: 0;
  color: #94a3b8;
  font-size: 0.8rem;
  line-height: 1.4;
}
</style>
