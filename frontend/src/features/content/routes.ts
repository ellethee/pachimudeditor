import type { RouteRecordRaw } from 'vue-router'
import { mdiAccountGroup, mdiBookOpenPageVariant, mdiClipboardCheckOutline, mdiEmoticonOutline, mdiMagicStaff, mdiSwordCross, mdiTable } from '@quasar/extras/mdi-v7'

export default [
  {
    path: '/content/check',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.check.title',
      descriptionKey: 'content.check.description',
      icon: mdiClipboardCheckOutline,
      order: 79,
      pageScroll: true,
    },
    component: () => import('./pages/CheckPage.vue'),
  },
  {
    path: '/content/races',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.races.title',
      descriptionKey: 'content.races.description',
      icon: mdiAccountGroup,
      order: 80,
      pageScroll: true,
    },
    component: () => import('./pages/RacesPage.vue'),
  },
  {
    path: '/content/classes',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.classes.title',
      descriptionKey: 'content.classes.description',
      icon: mdiSwordCross,
      order: 81,
      pageScroll: true,
    },
    component: () => import('./pages/ClassesPage.vue'),
  },
  {
    path: '/content/skills',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.skills.title',
      descriptionKey: 'content.skills.description',
      icon: mdiMagicStaff,
      order: 82,
      pageScroll: true,
    },
    component: () => import('./pages/SkillsPage.vue'),
  },
  {
    path: '/content/socials',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.socials.title',
      descriptionKey: 'content.socials.description',
      icon: mdiEmoticonOutline,
      order: 83,
      pageScroll: true,
    },
    component: () => import('./pages/SocialsPage.vue'),
  },
  {
    path: '/content/tables',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.tables.title',
      descriptionKey: 'content.tables.description',
      icon: mdiTable,
      order: 84,
      pageScroll: true,
    },
    component: () => import('./pages/TablesPage.vue'),
  },
  {
    path: '/content/catalogs',
    meta: {
      capability: 'supportsContentRaces',
      titleKey: 'content.catalogs.title',
      descriptionKey: 'content.catalogs.description',
      icon: mdiBookOpenPageVariant,
      order: 85,
      pageScroll: true,
    },
    component: () => import('./pages/CatalogsPage.vue'),
  },
] as RouteRecordRaw[]
