<script setup>
import UiSelect from '../UiSelect.vue'
import ExternalBackupSettings from '../ExternalBackupSettings.vue'
const props = defineProps({ controller: { type: Object, required: true }, form: { type: Object, required: true }, snapshot: { type: Object, required: true }, saving: Boolean, formatBytes: Function, formatWhen: Function })
const emit = defineEmits(['save'])
const patchSettings = payload => emit('save', payload)
const { backups, backupInfo, backupJob, restoreTarget, uploading, backupJobRunning, backupOnConfigVolume, backupJobPercent, stopJobPoll, watchJob, createBackup, verifyBackup, openRestore, toggleRestoreSection, confirmRestore, downloadBackup, uploadBackup, deleteBackup, backupKindLabel } = props.controller
</script>
<template>
  <div class="settings-section">
      <ExternalBackupSettings />
      <div class="glass-card settings-card">
        <div class="settings-card-head">
          <h3>{{ $t('Backups') }}</h3>
          <p>
            {{ $t('Manager settings, secrets, app config and databases. Media, downloads, caches, logs and artwork caches are never included. Databases are copied safely while apps keep running.') }}
          </p>
        </div>
        <p class="share-meta">
          {{ $t('Stored in') }} <span class="font-mono">{{ backupInfo.backup_dir || snapshot.backup_dir }}</span>
          {{ $t('· last backup') }} {{ formatWhen(backupInfo.schedule?.last_backup_at) }}
          <span v-if="backupInfo.schedule?.last_error" class="backup-warn"> {{ $t('· last attempt failed:') }} {{ backupInfo.schedule.last_error }}</span>
        </p>
        <p v-if="backupOnConfigVolume" class="settings-hint">
          {{ $t('Backups sit on the same volume as /config. Map a separate disk or NAS share to') }} <code>/backups</code>
          {{ $t('(or set') }} <code>AMM_BACKUP_DIR</code>{{ $t(') so a failed disk does not take the backups with it, or download them regularly.') }}
        </p>

        <div v-if="backupJob && (backupJobRunning || backupJob.status === 'error')" class="backup-job">
          <strong>{{ backupJob.kind }} · {{ backupJob.stage }}</strong>
          <div v-if="backupJobRunning" class="backup-progress"><span :style="{ width: `${backupJobPercent}%` }"></span></div>
          <span v-if="backupJobRunning && backupJob.total" class="path-line">{{ backupJob.done }} / {{ backupJob.total }} files</span>
          <span v-if="backupJob.status === 'error'" class="backup-warn">{{ backupJob.error }}</span>
        </div>

        <form class="form-stack" @submit.prevent="patchSettings({
          backup_retention: Number(form.backup_retention),
          backup_schedule: form.backup_schedule,
          backup_time: form.backup_time,
          backup_weekday: Number(form.backup_weekday),
          backup_day_of_month: Number(form.backup_day_of_month)
        })">
          <label class="ui-field">{{ $t('Automatic backups') }}
            <UiSelect
              v-model="form.backup_schedule"
              :options="[
                { value: 'off', label: $t('Off') },
                { value: 'daily', label: $t('Daily') },
                { value: 'weekly', label: $t('Weekly') },
                { value: 'monthly', label: $t('Monthly') },
              ]"
            />
          </label>
          <label v-if="form.backup_schedule !== 'off'" class="ui-field">{{ $t('Time of day') }}
            <input v-model="form.backup_time" type="time" class="ui-input font-mono" />
          </label>
          <label v-if="form.backup_schedule === 'weekly'" class="ui-field">{{ $t('Weekday') }}
            <UiSelect
              v-model="form.backup_weekday"
              :options="[
                { value: 0, label: $t('Monday') },
                { value: 1, label: $t('Tuesday') },
                { value: 2, label: $t('Wednesday') },
                { value: 3, label: $t('Thursday') },
                { value: 4, label: $t('Friday') },
                { value: 5, label: $t('Saturday') },
                { value: 6, label: $t('Sunday') },
              ]"
            />
          </label>
          <label v-if="form.backup_schedule === 'monthly'" class="ui-field">{{ $t('Day of month') }}
            <input v-model.number="form.backup_day_of_month" type="number" min="1" max="28" class="ui-input font-mono" />
          </label>
          <label class="ui-field">{{ $t('Keep last N backups') }}
            <input v-model.number="form.backup_retention" type="number" min="1" max="90" class="ui-input font-mono" />
          </label>
          <div class="share-row">
            <button type="submit" class="ui-btn ui-btn-ghost" :disabled="saving">{{ $t('Save') }}</button>
            <button type="button" class="ui-btn ui-btn-primary" :disabled="backupJobRunning" @click="createBackup">{{ $t('Backup now') }}</button>
            <label class="ui-btn ui-btn-ghost backup-upload" :class="{ 'is-disabled': uploading || backupJobRunning }">
              {{ uploading ? $t("Uploading…") : $t("Upload backup") }}
              <input type="file" accept=".tar.gz,.tgz,application/gzip" :disabled="uploading || backupJobRunning" @change="uploadBackup" />
            </label>
          </div>
        </form>

        <div v-if="restoreTarget" class="backup-restore glass-card">
          <strong>{{ $t('Restore from') }} <span class="font-mono">{{ restoreTarget.name }}</span></strong>
          <p class="settings-hint">
            {{ $t('Pick everything or only some apps. The current state is backed up first, affected apps are stopped during the restore and started again afterwards.') }}
          </p>
          <div class="backup-sections">
            <label class="backup-chip">
              <input type="checkbox" :checked="restoreTarget.selected.includes('all')" @change="toggleRestoreSection('all')" />
              {{ $t('Everything') }}
            </label>
            <label v-for="item in restoreTarget.sections" :key="item" class="backup-chip">
              <input
                type="checkbox"
                :checked="restoreTarget.selected.includes(item)"
                @change="toggleRestoreSection(item)"
              />
              {{ item === 'manager' ? $t("Manager settings & secrets") : item }}
            </label>
          </div>
          <div class="share-row">
            <button type="button" class="ui-btn ui-btn-primary" @click="confirmRestore">{{ $t('Restore') }}</button>
            <button type="button" class="ui-btn ui-btn-ghost" @click="restoreTarget = null">{{ $t('Cancel') }}</button>
          </div>
        </div>

        <ul class="backup-list">
          <li v-for="item in backups" :key="item.name">
            <div>
              <strong class="font-mono">{{ item.name }}</strong>
              <span class="path-line">
                {{ backupKindLabel(item) }} · {{ formatWhen(item.created_at) }} · {{ formatBytes(item.size_bytes) }}
                <template v-if="item.file_count"> · {{ item.file_count }} files</template>
                <template v-if="item.location === 'legacy'"> {{ $t('· old location') }}</template>
                <template v-if="item.format < 2"> {{ $t('· old format') }}</template>
              </span>
              <span v-if="item.warnings.length" class="path-line backup-warn" :title="item.warnings.join('\n')">
                {{ item.warnings.length }} {{ $t('warning(s):') }} {{ item.warnings[0] }}
              </span>
            </div>
            <div class="share-row">
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="openRestore(item.name)">{{ $t('Restore') }}</button>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="verifyBackup(item.name)">{{ $t('Verify') }}</button>
              <button type="button" class="ui-btn ui-btn-ghost" @click="downloadBackup(item.name)">{{ $t('Download') }}</button>
              <button type="button" class="ui-btn ui-btn-ghost" :disabled="backupJobRunning" @click="deleteBackup(item.name)">{{ $t('Delete') }}</button>
            </div>
          </li>
          <li v-if="!backups.length" class="share-idle">{{ $t('No backups yet.') }}</li>
        </ul>
      </div>
  </div>
</template>
<style scoped src="./settingsForms.css"></style>
<style scoped src="./backups.css"></style>
<style scoped>.settings-section { display: contents; }</style>
