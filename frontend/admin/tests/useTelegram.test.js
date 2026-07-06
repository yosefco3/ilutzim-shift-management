import { describe, it, expect, beforeEach, afterAll } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useTelegram } from '../src/hooks/useTelegram';

describe('useTelegram', () => {
  const originalTelegram = window.Telegram;

  beforeEach(() => {
    delete window.Telegram;
  });

  afterAll(() => {
    window.Telegram = originalTelegram;
  });

  it('should detect dev mode when Telegram is not available', () => {
    const { result } = renderHook(() => useTelegram());
    expect(result.current.isDevMode).toBe(true);
    expect(result.current.initData).toBe('__DEV_MODE__');
    expect(result.current.user.id).toBe('dev-user');
  });

  it('should detect Telegram context when available', () => {
    window.Telegram = {
      WebApp: {
        initData: 'real-init-data',
        initDataUnsafe: {
          user: { id: 12345, first_name: 'יעקב', last_name: 'כהן' },
        },
        themeParams: { bg_color: '#ffffff' },
      },
    };

    const { result } = renderHook(() => useTelegram());
    expect(result.current.isDevMode).toBe(false);
    expect(result.current.initData).toBe('real-init-data');
    expect(result.current.user.first_name).toBe('יעקב');
  });

  it('should provide mainButton API with no-op in dev mode', () => {
    const { result } = renderHook(() => useTelegram());
    // Should not throw
    expect(() => result.current.mainButton.show('Test')).not.toThrow();
    expect(() => result.current.mainButton.hide()).not.toThrow();
    expect(() => result.current.mainButton.onClick(() => {})).not.toThrow();
  });

  it('should provide close function with no-op in dev mode', () => {
    const { result } = renderHook(() => useTelegram());
    expect(() => result.current.close()).not.toThrow();
  });
});